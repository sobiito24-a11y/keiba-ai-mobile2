"""Read-only, horse-keyed NAR evidence; past-run joins only reuse data utilities."""
import math
import re
from datetime import datetime, timezone, timedelta
from .nar_ability_rank import canonical_nar_ability_rank
from .jra_repro_candidate import merged_runs
from .newspaper_v2_inputs import result_rows, race_id

def num(v):
 if isinstance(v,bool):return None
 try:
  n=float(v);return n if math.isfinite(n) else None
 except (ValueError,TypeError):return None


def pick(row,*keys):
 for k in keys:
  v=row.get(k)
  if v is not None and str(v).strip() not in ('','None','nan','—','未取得'):return v
 return None


def stamp(value):
 try:
  t=datetime.fromisoformat(str(value));return t if t.tzinfo else t.replace(tzinfo=timezone(timedelta(hours=9)))
 except (ValueError,TypeError):return None


def nar_material_inputs(result, *, saved_rows=None):
 info=result.race_info or {};day=str(info.get('race_date') or info.get('date') or '')[:10]
 start=stamp(info.get('scheduled_post_time') or info.get('scheduled_start_time'))
 if start is None:
  m=re.search(r'(\d{1,2}:\d\d)発走',str(info.get('race_data') or info.get('raw') or ''))
  if m:start=stamp(day+'T'+m[1])
 created=stamp(result.created_at)
 if not created or not start:return None,'発走前時刻の確認不能'
 if created>=start:return None,'発走後生成'
 source=saved_rows if saved_rows is not None else result_rows(result);N=len(source);horses=[]
 seen=set()
 for r in source:
  horse_number=num(pick(r,'horse_no','馬番'))
  if horse_number is None or not horse_number.is_integer() or horse_number<1:
   raise ValueError('missing or invalid horse number')
  no=str(int(horse_number))
  if no in seen:raise ValueError('duplicate horse')
  seen.add(no)
  runs,audit=merged_runs({},r,day)
  # Explicit input contract: current outcomes, odds/popularity never copied.
  h={'horse_no':no,'horse_name':pick(r,'horse_name','馬名'),
     'ability_rank':canonical_nar_ability_rank(r),
     'ability':num(pick(r,'ver3_ability_core','_ver3_ability_core','market_ability_score','ability_value')),
     'distance':num(pick(r,'距離指数','distance_index')),'course':num(pick(r,'コース指数','course_index')),
     'corner4':num(pick(r,'netkeiba_corner4_rank','_netkeiba_corner4_rank')),
     'pace':pick(r,'provider_pace_market','netkeiba_pace','_netkeiba_pace'),
     'jockey_rate':num(pick(r,'jockey_course_top3_rate','_jockey_course_place_rate')),
     'jockey_runs':num(pick(r,'jockey_course_runs','_jockey_course_starts')),
     'style':pick(r,'脚質','running_style_market'),
     'load_weight':num(pick(r,'_current_load_weight','斤量')),
     'load_change':num(pick(r,'weight_change_market','_load_weight_change')),
     'sex_age':pick(r,'性齢','馬年齢','sex_age'),
     'legacy_class_reference_only':pick(r,'class_shift_market','クラス変動'),
     'runs':runs, 'missing_runs_reason':audit['missing_reason']}
  venue=info.get('racecourse') or info.get('venue');distance=num(info.get('distance'))
  for field,same in [('star',True),('away',False)]:
   values=[num(x.get('value')) for x in runs if num(x.get('value')) is not None and distance is not None
           and x.get('distance')==distance and venue and x.get('venue') and (x['venue']==venue)==same]
   h[field]=max(values) if values else None
  horses.append(h)
 for key in ['distance','course','star','away']:
  values=[h[key] for h in horses if h[key] is not None]
  for h in horses:h[key+'_rank']=1+sum(v>h[key] for v in values) if h[key] is not None else None
 return {'race_id':race_id(result),'date':day,'venue':info.get('venue') or info.get('racecourse'),
         'created_at':result.created_at,'scheduled_start':start.isoformat(),'horses':horses},None
