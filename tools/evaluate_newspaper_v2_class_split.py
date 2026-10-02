"""Frozen v1 / class split / ablation comparison. Outputs only to --output.

Inputs are the prior validation source_manifest, class_audit, comparison and
v2_reference_replays. No result information enters feature computation.
"""
from __future__ import annotations
import argparse
import copy
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.evaluate_newspaper_v2_shadow import read_races, frozen_rows, write_csv
from core.newspaper_v2_engine import evaluate_shadow
from core.newspaper_v2_class_revision import evaluate_class_revision, without_class_reference
from core.newspaper_v2_inputs import number


def read_csv(path):
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def normalized(payload):
    data=copy.deepcopy(payload);data.pop("evaluated_at",None);return data


def evaluate(root,output):
    root=Path(root);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    source_manifest=json.loads((root/'evaluation/source_manifest.json').read_text(encoding='utf-8'))
    frozen={x['race_id']:x['shadow'] for x in json.loads((root/'evaluation/v2_reference_replays.json').read_text(encoding='utf-8'))}
    metadata={x['race_id']:x for x in read_csv(root/'evaluation/class_audit.csv')}
    comparison=defaultdict(dict)
    for row in read_csv(root/'evaluation/horse_comparison.csv'):comparison[row['race_id']][row['horse_no']]=row
    inputs={str(root/'evaluation/v2_reference_replays.json'):sha(root/'evaluation/v2_reference_replays.json')}
    for path in ['evaluation/source_manifest.json','evaluation/class_audit.csv','evaluation/horse_comparison.csv']:
        inputs[str(root/path)]=sha(root/path)
    horses=[];race_rows=[];metrics=defaultdict(list);features=defaultdict(list);causes=defaultdict(set)
    swaps=[];winner_changes=[];replays=[]
    for source in source_manifest:
      path=Path(source['path']);assert sha(path)==source['sha256'];inputs[str(path)]=sha(path)
      for race in read_races(path):
        rid=race['race_id'];mode=race['race_mode'];p=mode+'_v2_';meta=metadata[rid]
        rows=frozen_rows(race);info={**race['prediction_result'].get('race_info',{}),'race_name':race.get('race_name'),'race_id':rid}
        htmlpath=Path(meta['header_source']);html=htmlpath.read_text(encoding='utf-8-sig') if htmlpath.is_file() else ''
        if html:inputs[str(htmlpath)]=sha(htmlpath)
        base=frozen[rid];v1=evaluate_shadow(rows,info,mode,html=html,race_identifier=rid)
        assert normalized(base)==normalized(v1),(rid,'v1 changed')
        old=copy.deepcopy(base)
        revised=evaluate_class_revision(rows,info,mode,html=html,base_v1=base)
        ablated=without_class_reference(base)
        assert base==old
        replays.append({'race_id':rid,'provenance':'development_reference_recalculation_only','revision':revised,'ablation':ablated})
        oldby={h['horse_no']:h for h in base['horses']};newby={h['horse_no']:h for h in revised['horses']}
        official_field='frozen_official_top5' if mode=='jra' else 'frozen_pure_ability'
        official={no:number(row[official_field]) for no,row in comparison[rid].items()}
        assert set(official)==set(oldby)==set(newby)
        ranks={'official':official}
        for label,payload in [('v1',base),('split',revised),('no_class',ablated)]:
          for purpose in ['top5','win']:
            ranks[label+'_'+purpose]={h['horse_no']:h[p+purpose+'_candidate_rank'] for h in payload['horses']}
        included=all(all(v is not None for v in rank.values()) for rank in ranks.values()) and base['status']=='ok'
        identity={'race_id':rid,'mode':mode,'date':meta['date'],'venue':meta['venue'],'race_number':int(rid[-2:]),'race_name':meta['race_name'],'paired':included}
        # Supplementary coverage uses precisely the same saved inputs without HTML.
        saved_v1=evaluate_shadow(rows,info,mode,html='',race_identifier=rid)
        saved_split=evaluate_class_revision(rows,info,mode,html='',base_v1=saved_v1)
        for source_kind,payload,parent in [('with_saved_html',revised,base),('snapshot_only',saved_split,saved_v1)]:
          parent_by={h['horse_no']:h for h in parent['horses']}
          for h in payload['horses']:
            no=h['horse_no'];audit=h['class_revision'];ev=audit['previous_evidence'];oldh=parent_by[no]
            vals={'v1_class_finish':oldh[p+'class_score'],'finish_quality':h[p+'finish_quality_score'],'class_change':h[p+'class_change_score'],
                  'any_split_feature':1 if h[p+'finish_quality_score'] is not None or h[p+'class_change_score'] is not None else None,
                  'previous_head_count':number(ev.get('head_count')),'previous_finish':number(ev.get('finish')),
                  'newly_available':1 if oldh[p+'class_score'] is None and (h[p+'finish_quality_score'] is not None or h[p+'class_change_score'] is not None) else None}
            reasons={'v1_gate':audit['v1_invalid_reasons'],'split_finish':audit['finish_invalid_reasons'],'split_transition':audit['transition_invalid_reasons']}
            # Surface omissions and raw parsing failures are distinct audit facts.
            if oldh[p+'class_score'] is None:
              reasons['v1_gate']=list(dict.fromkeys(reasons['v1_gate']+audit['finish_invalid_reasons']))
            for cohort in ['all_available']+(['paired'] if included else []):
              for day in [meta['date'],'ALL']:
                for feature,value in vals.items():features[(mode,day,cohort,source_kind,feature)].append((rid,no,value))
                for stage,flags in reasons.items():
                  for flag in flags:causes[(mode,day,cohort,source_kind,stage,flag)].add((rid,no))
            horse_row={**identity,'source':source_kind,'horse_no':no,'horse_name':h['horse_name'],
                'v1_class_finish':oldh[p+'class_score'],'finish_quality':h[p+'finish_quality_score'],'class_change':h[p+'class_change_score'],
                'previous_finish':ev.get('finish'),'previous_head_count':ev.get('head_count'),
                'data01_raw':ev.get('data01_raw'),'data03_raw':ev.get('data03_raw'),'data04_raw':ev.get('data04_raw'),'data05_raw':ev.get('data05_raw'),
                'class_badge_raw':ev.get('class_badge_raw'),'v1_previous_class':audit['v1_previous_class']['class_label_v2'],
                'revised_previous_class':audit['previous_class']['class_label_v2'],
                'previous_age':audit['previous_class']['age_restriction_v2'],
                'previous_family':audit['previous_class']['class_family'],'previous_discipline':audit['previous_class']['race_discipline_v2'],
                'previous_venue':audit['previous_class']['venue_v2'],
                'v1_invalid_reasons':json.dumps(reasons['v1_gate'],ensure_ascii=False),
                'finish_invalid_reasons':json.dumps(reasons['split_finish'],ensure_ascii=False),
                'transition_invalid_reasons':json.dumps(reasons['split_transition'],ensure_ascii=False)}
            for purpose,c in audit['contributions'].items():
              for key,value in c.items():horse_row[purpose+'_'+key+'_contribution']=value
            horses.append(horse_row)
        # Outcomes are looked up only after every prediction computation above.
        finishes={no:number(row['finish']) for no,row in comparison[rid].items()}
        winners={no for no,finish in finishes.items() if finish==1}
        race_rows.append({**identity,'horse_count':len(rows),'status':base['status'],
            'exclusion_reasons': '' if included else ' / '.join([k+': missing ranks '+','.join(no for no,v in r.items() if v is None) for k,r in ranks.items() if any(v is None for v in r.values())]),
            'v1_class_valid':sum(h[p+'class_score'] is not None for h in base['horses']),
            'split_finish_valid':sum(h[p+'finish_quality_score'] is not None for h in revised['horses']),
            'split_transition_valid':sum(h[p+'class_change_score'] is not None for h in revised['horses'])})
        if included:
          assert winners,(rid,'result missing')
          for model,rank in ranks.items():
            for no in winners:
              for dimension,value in [('all','ALL'),('date',meta['date']),('venue',meta['venue'])]:metrics[(mode,model,dimension,value)].append(rank[no])
          for purpose in ['top5','win']:
            target=ranks['split_'+purpose];newset={n for n,v in target.items() if v<=5}
            for baseline in ['official','v1_'+purpose]:
              previous=ranks[baseline];oldset={n for n,v in previous.items() if v<=5}
              for no in sorted(oldset^newset,key=int):
                h=newby[no];audit=h['class_revision']
                swaps.append({**identity,'purpose':purpose,'baseline':baseline,'horse_no':no,'horse_name':h['horse_name'],
                  'change':'added' if no in newset else 'removed','before_rank':previous[no],'after_rank':target[no],
                  'pure_ability':h[p+'ability_anchor'],'finish':finishes[no],
                  'finish_quality':h[p+'finish_quality_score'],'class_change':h[p+'class_change_score'],
                  'contributions':json.dumps(audit['contributions'][purpose],ensure_ascii=False),
                  'reasons':json.dumps(h[p+'positive_reasons']+h[p+'negative_reasons'],ensure_ascii=False)})
              for no in winners:
                if previous[no]!=target[no]:
                  winner_changes.append({**identity,'purpose':purpose,'baseline':baseline,'horse_no':no,'horse_name':newby[no]['horse_name'],
                    'before_rank':previous[no],'after_rank':target[no],
                    'top5_effect':'rescued' if previous[no]>5>=target[no] else 'lost' if target[no]>5>=previous[no] else 'rank_only',
                    'top3_effect':'improved' if previous[no]>3>=target[no] else 'worsened' if target[no]>3>=previous[no] else 'unchanged',
                    'top1_effect':'improved' if previous[no]>1==target[no] else 'worsened' if target[no]>1==previous[no] else 'unchanged',
                    'contributions':json.dumps(newby[no]['class_revision']['contributions'][purpose],ensure_ascii=False),
                    'reasons':json.dumps(newby[no][p+'positive_reasons']+newby[no][p+'negative_reasons'],ensure_ascii=False)})
        if len(race_rows)%25==0:print(len(race_rows),'races validated',flush=True)
    # Per-race counts let every aggregate be traced back to specific horses.
    audit_by_race=defaultdict(list)
    for h in horses:
        if h['source']=='with_saved_html':audit_by_race[h['race_id']].append(h)
    for r in race_rows:
        flags=Counter()
        for h in audit_by_race[r['race_id']]:
            for field in ['v1_invalid_reasons','finish_invalid_reasons','transition_invalid_reasons']:
                for reason in json.loads(h[field]):flags[field+':'+reason]+=1
        r['invalid_reason_counts']=json.dumps(dict(flags),ensure_ascii=False)
    summaries=[]
    for (mode,model,dimension,value),ranks in sorted(metrics.items()):
        n=len(ranks);summaries.append(dict(mode=mode,model=model,dimension=dimension,value=value,races=n,
          top1=sum(r<=1 for r in ranks),top3=sum(r<=3 for r in ranks),top5=sum(r<=5 for r in ranks),mean_winner_rank=sum(ranks)/n))
    coverage=[]
    for (mode,day,cohort,source,feature),vals in sorted(features.items()):
        valid=sum(v is not None for _,_,v in vals)
        coverage.append(dict(mode=mode,date=day,cohort=cohort,source=source,feature=feature,horses=len(vals),valid=valid,
                             valid_rate=valid/len(vals),nonzero=sum(v is not None and v!=0 for _,_,v in vals)))
    reason_rows=[]
    for (mode,day,cohort,source,stage,reason),items in sorted(causes.items()):
        reason_rows.append(dict(mode=mode,date=day,cohort=cohort,source=source,stage=stage,reason=reason,horse_count=len(items),race_count=len({rid for rid,_ in items})))
    for name,data in [('class_split_horse_audit',horses),('class_split_race_audit',race_rows),('class_split_metrics',summaries),
                      ('class_split_feature_coverage',coverage),('class_split_invalid_reasons',reason_rows),('class_split_top5_swaps',swaps),('class_split_winner_changes',winner_changes)]:
        write_csv(output/(name+'.csv'),data)
    (output/'class_split_replays.json').write_text(json.dumps(replays,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    for path,before in inputs.items():assert sha(Path(path))==before,path
    (output/'input_hashes.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2),encoding='utf-8')
    counts=Counter(r['mode'] for r in race_rows if r['paired']);assert counts=={'jra':18,'nar':156},counts
    lines=['# 新聞型V2 クラス・着順分離候補 比較報告','',
      '正式予想は不変。v1を保持し、別versionの研究候補とクラス除去参考モデルを比較。結果最適化なし。過去診断であり未来検証ではありません。',
      '', '## 評価式', '',
      'A = 1 − 2×(前走着順−1)/(前走頭数−1)。有効な整数着順・頭数だけで計算。',
      'B = clip((前走クラス水準−今回クラス水準)/体系別尺度, -1, 1)。年齢・体系・開催場・平地/障害の比較根拠が揃う時のみ計算。',
      '新寄与 = 旧class係数 × (0.5×A + 0.5×B)。欠損項の寄与は0で、残る側の重みを増やさない。旧class最大幅は維持。',
      'JRA/NARともTop5候補のA/B係数は各0.25、勝ち馬候補は各0.375。他の係数と評価値はv1のまま。',
      'v1_no_classは旧class項だけを除去。修正版の解析や新特徴は混ぜません。',
      '', '## 同一母集団の成績', '', '|系統|モデル|R|Top1|Top3|Top5|平均勝ち馬順位|','|---|---|---:|---:|---:|---:|---:|']
    for x in summaries:
      if x['dimension']=='all':lines.append(f"|{x['mode']}|{x['model']}|{x['races']}|{x['top1']}|{x['top3']}|{x['top5']}|{x['mean_winner_rank']:.4f}|")
    lines+=['','比較JRA18Rは9/27のみ。9/26の20Rは正式順位が全頭分揃わず除外（障害1Rを含む）、9/27障害1Rも除外。NAR156Rは佐賀9/26 1Rの純能力欠損1Rを除外。全196Rの監査も別途保持。',
      '正式Top5は保存順位<=5で判定し、NARの5位同着による6頭選出を勝手に5頭へ削りません。',
      '', '## 特徴量有効率（比較母集団）','', '|系統|入力|項目|有効/頭数|','|---|---|---|---:|']
    for x in coverage:
      if x['date']=='ALL' and x['cohort']=='paired':lines.append(f"|{x['mode']}|{x['source']}|{x['feature']}|{x['valid']}/{x['horses']}|")
    lines+=['','## 無効原因（重複あり）','','|系統|段階|原因|頭数|R数|','|---|---|---|---:|---:|']
    for x in reason_rows:
      if x['date']=='ALL' and x['cohort']=='paired' and x['source']=='with_saved_html':lines.append(f"|{x['mode']}|{x['stage']}|{x['reason']}|{x['horse_count']}|{x['race_count']}|")
    lines+=['','Data03は主に定量/馬齢等。過去走クラスは最初のPastDataLine内のIcon_GradeType表示から取得。Data05の頭数・Data04の着順は原文を馬別CSVに保存。過去クラスの年齢区分を馬の年齢から推測していません。',
      'v1_gateは当時の抽出・ゲートを監査。split_transitionは正しい過去会場からJRA/NARを識別し、表面上の一致を防止する厳密な比較不能理由。件数は重複あり。',
      '', '## 勝ち馬のTop5捕捉が変化したレース','', '|系統|race_id|会場/R|基準|順位系統|馬番・名|前→後|効果|','|---|---|---|---|---|---|---|---|']
    for x in winner_changes:
      if x['top5_effect']!='rank_only':lines.append(f"|{x['mode']}|{x['race_id']}|{x['venue']}{x['race_number']}R|{x['baseline']}|{x['purpose']}|{x['horse_no']} {x['horse_name']}|{x['before_rank']}→{x['after_rank']}|{x['top5_effect']}|")
    lines+=['','勝ち馬の全順位変動・Top1/Top3改善悪化はclass_split_winner_changes.csv、全入替馬と理由はclass_split_top5_swaps.csv。日付/会場別はclass_split_metrics.csv。各馬のA/B/旧class寄与と増減はclass_split_horse_audit.csv。',
      '', '## 保存と不変性', '',
      '修正版は *_newspaper_v2_class_split_shadow に追加。既存 *_newspaper_v2_shadow とv1モデル/係数は維持。研究パネルも既存v1を表示したまま。過去Snapshotの再計算・上書きは行いません。',
      f'入力 {len(inputs)}ファイルのSHA-256一致。既存v1全196Rは評価時刻以外完全一致。両repo全テスト・新規生成/保存復元/正式予想不変の最終結果は別途追記。',
      '', '## 判断', '',
      'Aの発動率改善は新聞情報を利用できるようになったことを示しますが、順位精度や回収率の改善とは別問題です。Bの比較根拠不足は引き続き不明扱いとし、正式採用・係数再調整は行いません。']
    (output/'CLASS_SPLIT_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Completed',dict(counts),len(horses),'audit rows',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validation-root',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();evaluate(args.validation_root,args.output)
