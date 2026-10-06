"""Jockey positive evidence only. Never computes rankings, marks or probabilities."""
import copy
import math
import re
import unicodedata

VERSION='jockey_positive_v1_20261006'
JOCKEY_POSITIVE_RULES={
 'jra':dict(absolute_place_rate=30.0,min_runs=20,upgrade_delta=15.0,upgrade_min_runs=20,shadow_absolute=25.0,shadow_upgrade=10.0),
 'nar':dict(absolute_place_rate=35.0,min_runs=20,upgrade_delta=15.0,upgrade_min_runs=20,shadow_absolute=30.0,shadow_upgrade=10.0)}

def text(v):
 return '' if v is None or str(v).strip() in ('','None','nan','—','<NA>') else str(v).strip()
def pick(r,*keys):
 return next((r[k] for k in keys if text(r.get(k))),None)
def number(v):
 if isinstance(v,bool):return None
 try:
  n=float(str(v).replace('%','').replace('％',''));return n if math.isfinite(n) else None
 except (ValueError,TypeError):return None

def sample(v):
 n=number(v)
 return int(n) if n is not None and n>=0 and n.is_integer() else None

def identity(v):
 return re.sub(r'[\s・･.．]','',unicodedata.normalize('NFKC',text(v)))

def inputs(row):
 # Exactly the existing displayed statistic, not a new jockey population.
 from .prediction_table_ui import jockey_place_text
 shown=jockey_place_text(row)
 match=re.search(r'(\d+(?:\.\d+)?)%',shown)
 rate=number(match[1]) if match else number(row.get('current_jockey_place_rate'))
 count=sample(pick(row,'jockey_course_runs','_jockey_course_starts','jockey_course_starts','騎手コース出走回数','current_jockey_sample_size'))
 if count is None:
  raw=text(row.get('jockey_course_sample_market'))
  m=re.search(r'(?:n=|^)(\d+)(?:走|$)',raw)
  if m:count=sample(m[1])
 from .market_compare import _jockey
 current,previous,status=_jockey(row)
 current=current or text(row.get('current_jockey_name'))
 previous=previous or text(row.get('previous_jockey_name'))
 explicit=text(pick(row,'jockey_change_status','jockey_change_market','jockey_change'))
 if explicit in ('継続','乗替'):status=explicit
 previous_rate=number(pick(row,'previous_jockey_place_rate','_previous_jockey_course_place_rate'))
 previous_count=sample(pick(row,'previous_jockey_sample_size','_previous_jockey_course_starts'))
 if rate is not None and not 0<=rate<=100:rate=None
 if previous_rate is not None and not 0<=previous_rate<=100:previous_rate=None
 return dict(current_jockey_name=current,current_jockey_place_rate=rate,current_jockey_sample_size=count,
  previous_jockey_name=previous,previous_jockey_place_rate=previous_rate,previous_jockey_sample_size=previous_count,
  jockey_change_status=status or '不明',jockey_stat_condition=text(pick(row,'_jockey_course_condition','jockey_course_condition')),
  jockey_previous_source='explicit_saved' if previous_rate is not None else 'missing',
  jockey_current_source='existing_display_course_stat',jockey_stat_identity=text(pick(row,'_jockey_course_html_name','current_jockey_name')) or current)

def evaluate(values,mode):
 rule=JOCKEY_POSITIVE_RULES[mode.lower()];h=dict(values)
 rate=h.get('current_jockey_place_rate');n=h.get('current_jockey_sample_size')
 prev=h.get('previous_jockey_place_rate');pn=h.get('previous_jockey_sample_size')
 absolute_available=rate is not None and n is not None
 change=h.get('jockey_change_status')=='乗替'
 upgrade_available=change and absolute_available and prev is not None and pn is not None
 delta=rate-prev if rate is not None and prev is not None else None
 absolute=absolute_available and n>=rule['min_runs'] and rate>=rule['absolute_place_rate']
 upgrade=upgrade_available and n>=20 and pn>=20 and delta>=15
 shadow_absolute=absolute_available and n>=20 and rule['shadow_absolute']<=rate<rule['absolute_place_rate']
 shadow_upgrade=upgrade_available and n>=20 and pn>=20 and 10<=delta<15
 reason=(f'＋ 騎手強化（複勝率{rate:g}% / 前走比 +{delta:g}pt）' if absolute and upgrade else
         f'＋ 騎手強（複勝率{rate:g}% / {n}走）' if absolute else
         f'＋ 騎手アップ（前走比 +{delta:g}pt）' if upgrade else '')
 h.update(jockey_place_rate_delta=delta,jockey_absolute_positive=bool(absolute),jockey_upgrade_positive=bool(upgrade),
  jockey_positive=bool(absolute or upgrade),jockey_positive_count=int(bool(absolute or upgrade)),
  jockey_shadow_absolute=bool(shadow_absolute),jockey_shadow_upgrade=bool(shadow_upgrade),jockey_positive_reason=reason,
  jockey_absolute_status='evaluated' if absolute_available else 'neutral_missing',
  jockey_upgrade_status='evaluated' if upgrade_available else 'not_changed' if h.get('jockey_change_status')=='継続' else 'neutral_missing',
  jockey_positive_version=VERSION)
 return h

def annotate(rows,mode):
 raw=[dict(r) for r in rows];data=[inputs(r) for r in raw];registry={}
 for h in data:
  if h['jockey_stat_condition'] and h['jockey_stat_identity'] and h['current_jockey_place_rate'] is not None and h['current_jockey_sample_size'] is not None:
   key=(identity(h['jockey_stat_identity']),h['jockey_stat_condition'])
   registry.setdefault(key,set()).add((h['current_jockey_place_rate'],h['current_jockey_sample_size']))
 for r,h in zip(raw,data):
  if h['previous_jockey_place_rate'] is None and h['previous_jockey_sample_size'] is None and h['previous_jockey_name'] and h['jockey_stat_condition']:
   candidates=registry.get((identity(h['previous_jockey_name']),h['jockey_stat_condition']),set())
   if len(candidates)==1:
    h['previous_jockey_place_rate'],h['previous_jockey_sample_size']=next(iter(candidates));h['jockey_previous_source']='same_race_saved_same_condition_exact_identity'
   elif len(candidates)>1:h['jockey_previous_source']='conflicting_saved_stats'
  r.update(evaluate(h,mode))
 return raw

def snapshot(result):
 saved=(getattr(result,'debug_info',None) or {}).get('jockey_positive_evidence')
 if isinstance(saved,dict):return copy.deepcopy(saved)
 from .jra_final_mark import horse_key
 merged={}
 for table in (getattr(result,'overall_table',None),getattr(result,'horse_evaluation',None)):
  if table is None:continue
  for row in table.to_dict('records'):
   key=horse_key(row)
   if not key:continue
   dest=merged.setdefault(key,{})
   for k,v in row.items():
    if not text(dest.get(k)) and text(v):dest[k]=v
 rows=annotate(list(merged.values()),result.race_mode)
 fields=set(evaluate(inputs({}),result.race_mode))
 return dict(model_version=VERSION,race_mode=result.race_mode,source='saved_prediction_inputs',
  rules=copy.deepcopy(JOCKEY_POSITIVE_RULES[result.race_mode]),
  horses=[dict(horse_no=horse_key(h),**{k:v for k,v in h.items() if k in fields}) for h in rows])

def overlay(result,rows):
 from .jra_final_mark import horse_key
 by={h['horse_no']:h for h in snapshot(result)['horses']}
 return [dict(h,**{k:v for k,v in by.get(horse_key(h),{}).items() if k!='horse_no'}) for h in rows]

def reason(row):
 return text(row.get('jockey_positive_reason'))


def attach(result):
 result.debug_info=dict(getattr(result,'debug_info',None) or {},jockey_positive_evidence=snapshot(result))
 return result
