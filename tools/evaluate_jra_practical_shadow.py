"""Offline research replay. Reads CSV features and results in separate stages.

The ZIP's 54R has already been explored. These are NOT future test predictions.
No training, coefficient search, saved-prediction writes or network access.
"""
import argparse
import csv
import json
from pathlib import Path
import sys
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.jra_practical_shadow import evaluate_practical_shadow, number, digest


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write(path, rows):
    if not rows:
        return
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer=csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)


def replay(research, output):
    features=read(research/'input/54R_全頭_条件特徴量と着順.csv')
    age={(r['race_id'],r['horse_no']):r for r in read(research/'input/54R_年齢クラス位置取り追加監査.csv')}
    outcomes={r['race_id']:r for r in read(research/'input/JRA_Top5境界入替_54R全レース監査.csv')}
    groups=defaultdict(list)
    for row in features:
        groups[row['race_id']].append(row)
    assert len(groups)==54 and len(features)==768
    output.mkdir(parents=True, exist_ok=True)
    payloads=[];races=[];horse_rows=[]
    for rid, original in sorted(groups.items()):
        rows=[]
        for r in original:
            h={'horse_no':r['horse_no'],'horse_name':r['horse_name'],
               'training_grade':r['training_grade'] or None, 'recent_runs':[], 'head_to_head':[],
               'sources':{'features':'research ZIP audited pre-race CSV (raw extraction not independently replayed)'},
               'age':number(age[(rid,r['horse_no'])]['age']), 'body_weight':None,
               'class_change':None, 'layoff_returns':[]}
            for key,source in [('formal_rank','formal_rank'),('formal_score','formal_score'),('pure_score','pure_score'),
                               ('pure_rank','pure_rank'),('corner4_rank','corner4_rank'),('rest_days','rest_days'),
                               ('load_change','load_change_kg'),('distance_index','distance_index'),('course_index','course_index'),
                               ('distance_rank','distance_index_rank_avail'),('course_rank','course_index_rank_avail')]:
                h[key]=number(r[source])
            # ★/☆, explicit prior-class age evidence and full H2H records are not
            # in the packaged feature CSV. Do not manufacture them from outcomes.
            h.update(star_index=None,away_index=None,star_rank=None,away_rank=None)
            rows.append(h)
        paces={r['pace'] for r in original if r['pace'] in ('S','M','H')}
        inputs={'race_id':rid,'race_date':original[0]['date'],'venue':original[0]['venue'],
                'pace':next(iter(paces)) if len(paces)==1 else None, 'time_status':'pre_race',
                'time_evidence':'research ZIP claims audited pre-race extraction; not future validation',
                'evaluation_context':'retrospective_reference_replay_54R_incomplete_feature_csv', 'horses':rows}
        p=evaluate_practical_shadow(inputs,evaluated_at='reference_replay_2026-10-05')
        payloads.append(p)
        # Outcome join happens only after evaluation.
        target=outcomes[rid]
        finish=target['finish'].split('-');winner=finish[0];top3=set(finish)
        assert set(p['A'])==set(target['top5_nos'].split('-'))
        assert len(top3)==3
        for label in ('A','B','C'):
            chosen=set(p[label]);assert len(chosen)==5
            hit=int(top3<=chosen)
            known=target['payout_known'] in ('1','True','true') and number(target['payout_actual_100']) is not None
            payout=number(target['payout_actual_100']) if hit and known else 0 if not hit else None
            races.append({'race_id':rid,'date':original[0]['date'],'venue':original[0]['venue'],
                          'race_name':original[0]['race_name'],'model':label,'horses':'-'.join(p[label]),
                          'added':'-'.join(sorted(chosen-set(p['A']),key=int)),
                          'removed':'-'.join(sorted(set(p['A'])-chosen,key=int)),
                          'winner_capture':int(winner in chosen),'top3_capture':len(top3&chosen),'trio_hit':hit,
                          'investment':1000,'payout':payout,'payout_source':target['source_url'],
                          'reason':p['protection_reason'] if label=='C' else 'frozen formal' if label=='A' else 'independent common-observed-domain reference'})
        for h in p['horses']:
            horse_rows.append({'race_id':rid,'date':original[0]['date'],'horse_no':h['horse_no'],'horse_name':h['horse_name'],
                               'formal_rank':h['formal_rank'],'formal_score':h['formal_score'],
                               'rank_range':json.dumps(h['shadow_rank_range']),'score_interval':json.dumps(h['score_interval']),
                               'classification':h['classification'], 'A':h['horse_no'] in p['A'],'B':h['horse_no'] in p['B'],'C':h['horse_no'] in p['C'],
                               'positive':' / '.join(h['positive_reasons']),'negative':' / '.join(h['negative_reasons']),
                               'missing':' / '.join(h['missing_reasons'])})
    summary=[]
    for day in ['all']+sorted({r['date'] for r in races}):
        for label in ('A','B','C'):
            items=[r for r in races if r['model']==label and (day=='all' or r['date']==day)]
            payout=sum(r['payout'] for r in items) if all(r['payout'] is not None for r in items) else None
            summary.append(dict(date=day,model=label,races=len(items),winner_capture=sum(r['winner_capture'] for r in items),
                                top3_capture=sum(r['top3_capture'] for r in items),trio_hit=sum(r['trio_hit'] for r in items),
                                swaps=sum(bool(r['added']) for r in items),payout=payout,
                                roi=payout/(len(items)*1000)*100 if payout is not None else None))
    write(output/'new_model_races.csv',races);write(output/'new_model_horses.csv',horse_rows)
    write(output/'new_model_summary.csv',summary)
    (output/'shadow_reference_payloads.json').write_text(json.dumps(payloads,ensure_ascii=False,indent=2),encoding='utf8')
    (output/'input_manifest.json').write_text(json.dumps({str(p):__import__('hashlib').sha256(p.read_bytes()).hexdigest()
                                                         for p in (research/'input').glob('*.csv')},ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--research',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();replay(args.research,args.output)
