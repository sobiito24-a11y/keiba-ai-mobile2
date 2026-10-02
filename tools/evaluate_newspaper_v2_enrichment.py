"""V3 input-quality audit; all replay outputs are reference recalculations."""
import argparse,copy,csv,json,sys
from collections import defaultdict,Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.evaluate_newspaper_v2_shadow import read_races,frozen_rows,write_csv
from tools.evaluate_newspaper_v2_class_split import read_csv,sha
from core.newspaper_v2_enrichment import evaluate_enriched,newspaper_runs,number,digest
from core.newspaper_v2_class_revision import rank_payload
from core.newspaper_v2_past_headers import parse_header,PastHeaderCache,collect_nar_header,NAR_BABA


def evaluate(root,output,fetch_limit=0,nar_fetch_limit=0):
 root=Path(root);output=Path(output);output.mkdir(parents=True,exist_ok=True)
 manifest=json.loads((root/'evaluation/source_manifest.json').read_text(encoding='utf-8'))
 metas={r['race_id']:r for r in read_csv(root/'evaluation/class_audit.csv')}
 old={r['race_id']:r['shadow'] for r in json.loads((root/'evaluation/v2_reference_replays.json').read_text(encoding='utf-8'))}
 split={r['race_id']:r for r in json.loads((root/'class_split_revision/class_split_replays.json').read_text(encoding='utf-8'))}
 comparisons=defaultdict(dict)
 for r in read_csv(root/'evaluation/horse_comparison.csv'):comparisons[r['race_id']][r['horse_no']]=r
 races=[];hashes={};headers={};htmls={}
 for f in ('evaluation/source_manifest.json','evaluation/v2_reference_replays.json','class_split_revision/class_split_replays.json','evaluation/horse_comparison.csv'):
  hashes[str(root/f)]=sha(root/f)
 for source in manifest:
  path=Path(source['path']);hashes[str(path)]=sha(path);assert hashes[str(path)]==source['sha256']
  races+=read_races(path)
 # Headers from local historical race pages only. Never read result table here.
 for race in races:
  rid=race['race_id'];path=Path(metas[rid]['header_source'])
  html=path.read_text(encoding='utf-8-sig') if path.is_file() else ''
  htmls[rid]=html
  if html:
   hashes[str(path)]=sha(path)
   header=parse_header(html,rid,source=str(path),known_info=race['prediction_result']['race_info'])
   if header:headers[rid]=header
 cache=PastHeaderCache(output/'past_header_cache',allow_http=bool(fetch_limit))
 needed=sorted({run['race_id'] for html in htmls.values() for runs in newspaper_runs(html).values() for run in runs if run.get('race_id')}-set(headers))
 attempted=0
 for rid in needed:
  cached=cache.get(rid) if attempted<fetch_limit or (cache.directory/(rid+'.json')).is_file() else None
  if cached:headers[rid]=cached
  attempted=len(cache.audit)
  # A server-wide access failure is not bypassed or hammered repeatedly.
  if len(cache.audit)>=3 and all(x.get('http_status') in (403,429) for x in cache.audit[-3:]):break
 (output/'header_collection_audit.json').write_text(json.dumps({'local_headers':len(headers),'missing_ids':needed,'http_attempts':cache.audit},ensure_ascii=False,indent=2),encoding='utf-8')
 # Official NAR headers resolve truncated newspaper classes; only past races.
 nar_runs={}
 for html in htmls.values():
  for runs in newspaper_runs(html).values():
   for run in runs:
    if run.get('race_id') and run.get('venue') in NAR_BABA:nar_runs.setdefault(run['race_id'],run)
 from concurrent.futures import ThreadPoolExecutor
 selected=list(nar_runs.values())
 selected.sort(key=lambda r:(not (output/'past_header_cache'/(r['race_id']+'.official.json')).is_file(),r['race_id']))
 def collect(run):
  local=root/'official_results'/(run['race_id']+'.html')
  worker=PastHeaderCache(output/'past_header_cache',allow_http=nar_fetch_limit>0)
  value=collect_nar_header(worker,run,local_html=local if local.is_file() else None)
  return run['race_id'],value,worker.audit
 jobs=[r for r in selected if (output/'past_header_cache'/(r['race_id']+'.official.json')).is_file() or (root/'official_results'/(r['race_id']+'.html')).is_file()]
 pending=[r for r in selected if r not in jobs]
 jobs+=pending[:nar_fetch_limit]
 with ThreadPoolExecutor(max_workers=3) as pool:
  for i,(rid,value,logs) in enumerate(pool.map(collect,jobs),1):
   cache.audit.extend(logs)
   if value:headers[rid]=value
   if i%50==0:print(i,'past official headers checked',flush=True)
 (output/'header_collection_audit.json').write_text(json.dumps({'available_headers':len(headers),'missing_ids':needed,'attempts':cache.audit},ensure_ascii=False,indent=2),encoding='utf-8')
 oldaudit=read_csv(root/'class_split_revision/class_split_horse_audit.csv')
 sixty={(r['race_id'],r['horse_no']) for r in oldaudit if r['mode']=='jra' and r['paired']=='True' and r['source']=='snapshot_only' and r['class_change']!=''}
 audit=[];merges=[];coverage=defaultdict(list);horseout=[];swaps=[];winners=[];metrics=defaultdict(list);sets=[];replays=[];invariance=[];exclusions=[]
 for race in races:
  rid=race['race_id'];mode=race['race_mode'];p=mode+'_v2_';meta=metas[rid]
  rows=frozen_rows(race);info={**race['prediction_result']['race_info'],'race_name':race['race_name'],'race_id':rid}
  before=digest([race,old[rid],split[rid]])
  revised=evaluate_enriched(rows,info,mode,html=htmls[rid],base_v1=old[rid],base_split=split[rid]['revision'],headers=headers,race_identifier=rid)
  assert before==digest([race,old[rid],split[rid]])
  b_control=copy.deepcopy(revised)
  for h in b_control['horses']:
   for purpose,w in b_control['coefficients'].items():
    key=p+purpose+'_candidate_score'
    if h[key] is not None:h[key]-=((h['input_enrichment']['b'] or 0)-(h['input_enrichment']['old_b'] or 0))*w['class_change']
  rank_payload(b_control)
  b_control_by={h['horse_no']:h for h in b_control['horses']}
  invariance.append({'race_id':rid,'horses':len(rows),'formal_v1_split_unchanged':True})
  replays.append({'race_id':rid,'provenance':'reference_recalculation_not_frozen_prediction','enriched':revised})
  rank={'official':{n:number(r['frozen_official_top5' if mode=='jra' else 'frozen_pure_ability']) for n,r in comparisons[rid].items()}}
  for name,payload in [('v1',old[rid]),('split',split[rid]['revision']),('enriched',revised),('no_class',split[rid]['ablation'])]:
   for purpose in ('top5','win'):rank[name+'_'+purpose]={h['horse_no']:h[p+purpose+'_candidate_rank'] for h in payload['horses']}
  included=old[rid]['status']=='ok' and all(all(v is not None for v in ranks.values()) for ranks in rank.values())
  ident={'race_id':rid,'mode':mode,'date':meta['date'],'venue':meta['venue'],'race_name':meta['race_name'],'paired':included}
  if not included:exclusions.append({**ident,'reason':old[rid]['status']+' / '+','.join(k for k,v in rank.items() if any(x is None for x in v.values()))})
  for h in revised['horses']:
   no=h['horse_no'];e=h['input_enrichment'];rr=h['structured_recent_runs'];first=rr[0] if rr else None
   ev=first['values'] if first else {};a=first['audit'] if first else {}
   for ix,r in enumerate(rr):merges.append({**ident,'horse_no':no,'horse_name':h['horse_name'],'past_slot':ix+1,'past_race_id':r['values'].get('race_id'),'status':r['audit']['status'],'identity_conflicts':json.dumps(r['audit']['identity_conflicts']),'field_conflicts':json.dumps(r['audit']['field_conflicts']),'temporal_status':r['audit']['temporal_status'],'provenance':json.dumps(r,ensure_ascii=False)})
   vals={'old_B':e['old_b'],'enriched_B':e['b'],'old_A':e['old_a'],'enriched_A':e['a'],'past_race_id':ev.get('race_id'),'past_date':ev.get('date'),'head_count':ev.get('head_count'),'past_age':None if e['previous_class']['age_restriction_v2']=='不明' else e['previous_class']['age_restriction_v2']}
   for component in ('ability_anchor','recent_form_score','condition_score','pace_score','training_score','jockey_score'):
    vals[component]=h.get(p+component)
   if included:
    for day in ('ALL',meta['date']):
     for key,val in vals.items():coverage[(mode,day,key)].append(val)
   if (rid,no) in sixty:
    cat='1_saved_correct_html_omitted' if e['b'] is not None and a.get('status') in ('race_id','composite') else '2_saved_comparison_conflicted' if a.get('identity_conflicts') or a.get('field_conflicts') else '3_insufficient_evidence'
    audit.append({**ident,'horse_no':no,'horse_name':h['horse_name'],'category':cat,'saved':json.dumps(a.get('saved'),ensure_ascii=False),'newspaper':json.dumps(a.get('newspaper'),ensure_ascii=False),'header':json.dumps(a.get('header'),ensure_ascii=False),'B':e['b'],'reasons':json.dumps(e['transition_flags'],ensure_ascii=False)})
   finish=number(comparisons[rid][no]['finish'])
   record={**ident,'horse_no':no,'horse_name':h['horse_name'],'finish':finish,'ability':h[p+'ability_anchor'],'ability_rank':comparisons[rid][no]['frozen_pure_ability'],**{key:vals[key] for key in ('old_A','old_B','enriched_A','enriched_B')},'new_B_available':e['old_b'] is None and e['b'] is not None,'B_only_before_top5_rank':b_control_by[no][p+'top5_candidate_rank'],'B_only_rank_changed':b_control_by[no][p+'top5_candidate_rank']!=h[p+'top5_candidate_rank'],'B_top5_contribution':(e['b'] or 0)*revised['coefficients']['top5']['class_change'],'B_win_contribution':(e['b'] or 0)*revised['coefficients']['win']['class_change'],'B_blockers':json.dumps(e['transition_flags']),**{key:r[no] for key,r in rank.items()}}
   horseout.append(record)
   if included:
    if finish==1:
     for model,r in rank.items():metrics[(mode,model)].append(r[no])
    for purpose in ('top5','win'):
     after=rank['enriched_'+purpose][no]
     for baseline in ('official','v1_'+purpose,'split_'+purpose):
      before_rank=rank[baseline][no]
      if (before_rank<=5)!=(after<=5):swaps.append({**record,'purpose':purpose,'baseline':baseline,'change':'added' if after<=5 else 'removed','before_rank':before_rank,'after_rank':after,'reasons':json.dumps(e,ensure_ascii=False)})
      if finish==1 and before_rank!=after:winners.append({**record,'purpose':purpose,'baseline':baseline,'before_rank':before_rank,'after_rank':after,'effect':'rescued' if before_rank>5>=after else 'lost' if after>5>=before_rank else 'rank_only','reasons':json.dumps(e,ensure_ascii=False)})
  if included:
   official={n for n,v in rank['official'].items() if v<=5};new={n for n,v in rank['enriched_top5'].items() if v<=5};union=official|new
   won={n for n,r in comparisons[rid].items() if number(r['finish'])==1}
   added=new-official
   sets.append({**ident,'official_size':len(official),'enriched_size':len(new),'rescue_union_size':len(union),'added':len(added),'added_wins':len(added&won),'added_places':sum(number(comparisons[rid][n]['finish']) in (1,2,3) for n in added),'winner_category':'both' if official&won and new&won else 'official_only' if official&won else 'enriched_only' if new&won else 'neither','official_top1_preserved_in_union':all(n in union for n,v in rank['official'].items() if v==1)})
  if len(invariance)%25==0:print(len(invariance),'races',flush=True)
 assert Counter(r['mode'] for r in sets)=={'jra':18,'nar':156}
 assert len(audit)==63,len(audit)
 cov=[{'mode':m,'date':d,'feature':f,'horses':len(v),'valid':sum(x is not None for x in v)} for (m,d,f),v in sorted(coverage.items())]
 for filename,data in [('jra_63horse_class_audit',audit),('past_race_input_coverage',cov),('snapshot_html_merge_audit',merges),('newspaper_v2_enriched_comparison',horseout),('newspaper_v2_enriched_top5_swaps',swaps),('newspaper_v2_enriched_winner_changes',winners),('rescue_union_comparison',sets),('excluded_races',exclusions)]:write_csv(output/(filename+'.csv'),data)
 (output/'enriched_replays.json').write_text(json.dumps(replays,ensure_ascii=False),encoding='utf-8')
 for path,expected in hashes.items():assert sha(Path(path))==expected,path
 (output/'invariance.json').write_text(json.dumps({'races':len(invariance),'horses':sum(r['horses'] for r in invariance),'checks':invariance,'input_hashes':hashes},ensure_ascii=False,indent=2),encoding='utf-8')
 lines=['# CLASS INPUT ENRICHMENT REPORT','','全結果は開発用の参考再計算。正式予想・v1・旧分離版・保存ファイルは不変。結果による係数調整なし。',
 'A/Bの式・各0.5の配分を維持。今回変えるのはA/B入力だけ。他のv1成分は凍結して比較。',
 '', '## 同一母集団比較', '', '|系統|モデル|R|Top1|Top3|Top5|平均勝ち馬順位|','|---|---|---:|---:|---:|---:|---:|']
 for (mode,model),r in sorted(metrics.items()):lines.append(f'|{mode}|{model}|{len(r)}|{sum(x<=1 for x in r)}|{sum(x<=3 for x in r)}|{sum(x<=5 for x in r)}|{sum(r)/len(r):.4f}|')
 lines+=['','## B入力・63頭監査','',str(Counter(r['category'] for r in audit)),'','|系統|項目|有効/頭数|','|---|---|---:|']
 for r in cov:
  if r['date']=='ALL':lines.append(f"|{r['mode']}|{r['feature']}|{r['valid']}/{r['horses']}|")
 lines+=['','## Top1保持・候補追加参考','']
 for mode in ('jra','nar'):
  group=[r for r in sets if r['mode']==mode];n=sum(r['added'] for r in group);wins=sum(r['added_wins'] for r in group);places=sum(r['added_places'] for r in group)
  lines.append(f"{mode}: {dict(Counter(r['winner_category'] for r in group))}。平均追加{n/len(group):.3f}頭、追加馬{n}頭、勝利{wins}・3着内{places}。全現行Top1を保持する集合和方式であり、候補数増による捕捉と同数順位改善は別。")
 lines+=['','## 情報源・限界','',f'利用ヘッダー{len(headers)}件（取得済みキャッシュを含む）。この実行の取得処理{len(cache.audit)}件。初回取得履歴はheader_collection_audit_first_pass.json、今回履歴はheader_collection_audit.json。',
 'Snapshotの過去race_idと新聞リンクを優先して照合。年はrace_idと月日から検証可能な形で復元。複合照合では年月日・場・R・馬識別・馬場・距離が必要。月日/スロットのみの結合は禁止。',
 '保存された拡張レース名の明示年齢条件は同一race_id・クラス整合時のみ使用。元HTML未保存の保存値は独立した原ページ照合済みとは区別する。取得時刻不明を予測時刻で埋めない。',
 '比較不能な年齢限定・新馬・異会場・体系差は欠損補完で数値化しない。全頭有効化を目的としない。',
 'JRA18Rは9/27平地のみ。9/26正式順位欠損20Rと9/27障害1Rを除外。NAR156Rは佐賀9/26 1Rの保存純能力欠損を除外。NAR5位同着6頭選出は維持。',
 f'全{len(invariance)}R・{sum(r["horses"] for r in invariance)}頭の元データと旧モデル非変更、全入力ファイルSHA一致。',
 '本候補の正式採用は行っていない。未来予測では保存済み構造化入力・結果を復元し、旧Snapshotには再計算を実行しない。']
 reasons=Counter((r['mode'],reason) for r in horseout if r['paired'] for reason in json.loads(r['B_blockers']))
 write_csv(output/'class_change_blockers.csv',[{'mode':m,'reason':reason,'horses':count} for (m,reason),count in sorted(reasons.items())])
 lines+=['','## Bによる変化（Aを固定した差分）','']
 for mode in ('jra','nar'):
  group=[r for r in horseout if r['paired'] and r['mode']==mode]
  newly=sum(r['new_B_available'] for r in group)
  changed=[r for r in group if r['B_only_rank_changed']]
  rescued=[r for r in group if r['finish']==1 and r['B_only_before_top5_rank']>5>=r['enriched_top5']]
  lost=[r for r in group if r['finish']==1 and r['enriched_top5']>5>=r['B_only_before_top5_rank']]
  lines.append(f"{mode}: 新たにB有効 {newly}頭、BによるTop5候補順位変化 {len(changed)}頭、勝ち馬追加捕捉 {len(rescued)}R、取りこぼし {len(lost)}R。")
  for r in rescued+lost:lines.append(f"- {r['race_id']} {r['venue']} {r['horse_no']} {r['horse_name']}: {r['B_only_before_top5_rank']}→{r['enriched_top5']}")
 write_csv(output/'class_B_rank_changes.csv',[r for r in horseout if r['paired'] and r['B_only_rank_changed']])
 lines+=['','取得可能率を上げるためのクラス推測はしていません。クラス原文が切れている／混合クラス／明示年齢不明／転入・異会場はclass_change_blockers.csvに分離しています。',
         'JRA63頭は保存過去race_idと新聞のID・条件が整合した保存情報の復元です。JRA過去ページHTTP 400のため、元ページを今回独立取得して年齢条件まで再確認した頭数とは区別してください。']
 (output/'CLASS_INPUT_ENRICHMENT_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print('\n'.join(lines[:25]),flush=True)

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--root',required=True);ap.add_argument('--output',required=True);ap.add_argument('--fetch-limit',type=int,default=0);ap.add_argument('--nar-fetch-limit',type=int,default=0);args=ap.parse_args();evaluate(args.root,args.output,args.fetch_limit,args.nar_fetch_limit)
