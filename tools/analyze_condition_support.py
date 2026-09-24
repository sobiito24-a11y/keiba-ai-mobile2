import sys,json,csv,hashlib,collections,math
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.prediction_table_ui import display_index_rows,horse_key
from core.nar_ability_rank import canonical_nar_ability_rank
from core.position_signals import is_jump_race
from core.v1_logic import jra_top5_sort_key
import argparse
parser=argparse.ArgumentParser(description="Frozen pre-race condition support replay; no production scoring changes")
parser.add_argument('--inputs',type=Path,required=True)
parser.add_argument('--results',type=Path,required=True)
parser.add_argument('--baseline',type=Path,required=True,help='Frozen current formal display rows keyed by race_id')
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args()
O=args.out;O.mkdir(parents=True,exist_ok=True)
inputs=json.loads(args.inputs.read_text(encoding='utf-8'))
results={r['race_id']:r for r in json.loads(args.results.read_text(encoding='utf-8'))}
base={r['race_id']:r for r in json.loads(args.baseline.read_text(encoding='utf-8'))}
def csvout(name,rows):
 if rows:
  with (O/name).open('w',newline='',encoding='utf-8-sig') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def stamp(v):
 try:return datetime.fromisoformat(v)
 except (TypeError,ValueError):return None
horse_rows=[];race_rows=[];excluded=[];eligible=[];scenarios=[];coverage=[]
for r in inputs:
 rid=r['race_id'];reason=None;created,start=stamp(r['created']),stamp(r['start'])
 if created is None or start is None:reason='時刻判定不能'
 elif not created<start:reason='発走前条件不成立'
 elif not Path(r['source']).is_file():reason='元Snapshotなし'
 elif r['mode']=='jra' and is_jump_race(r['info']):reason='JRA障害（平地と別扱い）'
 result=results.get(rid)
 if not reason and (not result or result.get('errors')):reason='確定結果未確認'
 finish=result.get('finish',[]) if result else []
 numeric=[h for h in finish if isinstance(h.get('finish'),int) and h['finish']>0]
 if not reason and not all(any(h['finish']==k for h in numeric) for k in (1,2,3)):reason='確定1〜3着不足'
 if reason:
  excluded.append(dict(race_id=rid,mode=r['mode'],date=r['date'],reason=reason));continue
 rows=base[rid]['rows'];numbers={horse_key(h) for h in rows}
 if any(str(h['horse_no']) not in numbers for h in numeric if h['finish']<=3):
  excluded.append(dict(race_id=rid,mode=r['mode'],date=r['date'],reason='上位結果馬が予想入力にない'));continue
 out=display_index_rows(rows,r['overall'],r['info'],r['mode'])
 eligible.append(dict(race_id=rid,mode=r['mode'],date=r['date'],source=r['source'],created=r['created'],start=r['start'],result_url=result.get('url'),result_sha256=result.get('raw_sha256')))
 lookup={str(h['horse_no']):h for h in finish}
 refunds={str(n) for n in result.get('refund_horses',[])}
 for h in out:
  n=horse_key(h);res=lookup.get(n);status=str(res.get('status','')) if res else ''
  if not res or status in ('取消','除外','') or n in refunds:continue
  rank=res.get('finish');win=int(rank==1);top3=int(isinstance(rank,int) and 1<=rank<=3)
  count=h[r['mode']+'_condition_support_count'];attention=h[r['mode']+'_condition_attention']
  formal_rank=h.get('jra_top5_rank') if r['mode']=='jra' else canonical_nar_ability_rank(h)
  horse_rows.append(dict(race_id=rid,mode=r['mode'],date=r['date'],venue=r['venue'],number=n,name=h.get('name',h.get('馬名','')),
    support_count=count,bucket=str(count) if count<3 else '3+',attention=attention,outside_attention=bool(attention and formal_rank is not None and formal_rank>5),formal_rank=formal_rank,
    finish=rank,win=win,top3=top3,distance_rank=h.get('distance_index_rank'),course_rank=h.get('course_index_rank'),star_value=h['star_index_value'],star_rank=h['star_index_rank'],away_value=h['away_same_distance_index_value'],away_rank=h['away_same_distance_index_rank'],shadow=h.get('jra_condition_support_shadow'),reason=h[r['mode']+'_condition_support_reason']))
 coverage.append(dict(race_id=rid,mode=r['mode'],date=r['date'],horses=len(out),star_available=sum(h['star_index_value'] is not None for h in out),away_available=sum(h['away_same_distance_index_value'] is not None for h in out)))
 if r['mode']=='jra':
  winners={str(h['horse_no']) for h in numeric if h['finish']==1}
  for cap in [0,.5,.75,1.0]:
   trial=[dict(h,jra_top5_score=round(h['jra_top5_score']+min(cap,h['jra_condition_support_shadow']),3)) for h in out]
   ordered=sorted(trial,key=jra_top5_sort_key)
   ranks=[i for i,h in enumerate(ordered,1) if horse_key(h) in winners]
   scenarios.append(dict(race_id=rid,date=r['date'],cap=cap,win1=int(min(ranks)<=1),win3=int(min(ranks)<=3),win5=int(min(ranks)<=5),winner_rank=sum(ranks)/len(ranks)))
summary=[]
for mode in ['jra','nar']:
 for date in ['ALL']+sorted({h['date'] for h in horse_rows if h['mode']==mode}):
  subset=[h for h in horse_rows if h['mode']==mode and (date=='ALL' or h['date']==date)]
  for group in ['0','1','2','3+','outside_attention','top5_0','top5_1','top5_2','top5_3+']:
   chosen=[h for h in subset if h['outside_attention']] if group=='outside_attention' else [h for h in subset if h['bucket']==group]
   if group.startswith('top5_'):
    chosen=[h for h in subset if h['formal_rank'] is not None and 1<=h['formal_rank']<=5 and h['bucket']==group[5:]]
   n=len(chosen);wins=sum(h['win'] for h in chosen);placed=sum(h['top3'] for h in chosen)
   summary.append(dict(mode=mode,date=date,group=group,horses=n,wins=wins,win_rate=wins/n if n else None,top3=placed,place_rate=placed/n if n else None,races=len({h['race_id'] for h in chosen})))
sim=[]
for date in ['ALL']+sorted({r['date'] for r in scenarios}):
 for cap in [0,.5,.75,1.0]:
  chosen=[r for r in scenarios if r['cap']==cap and (date=='ALL' or r['date']==date)]
  n=len(chosen)
  sim.append(dict(date=date,cap=cap,races=n,win1=sum(r['win1'] for r in chosen),win3=sum(r['win3'] for r in chosen),win5=sum(r['win5'] for r in chosen),mean_winner_rank=sum(r['winner_rank'] for r in chosen)/n if n else None))
for name,rows in [('horse_details.csv',horse_rows),('summary.csv',summary),('jra_simulation.csv',sim),('jra_simulation_races.csv',scenarios),('excluded.csv',excluded),('eligible.csv',eligible),('coverage.csv',coverage)]:csvout(name,rows)
payload=dict(summary=summary,simulation=sim,excluded=excluded,eligible_counts=dict(collections.Counter(r['mode'] for r in eligible)),exclusion_counts=dict(collections.Counter(r['reason'] for r in excluded)),input_sha256=hashlib.sha256(args.inputs.read_bytes()).hexdigest())
(O/'backtest.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in payload.items() if k not in ['summary','simulation','excluded']},ensure_ascii=False))
print(json.dumps([s for s in summary if s['date']=='ALL'],ensure_ascii=False))
print(json.dumps([s for s in sim if s['date']=='ALL'],ensure_ascii=False))
