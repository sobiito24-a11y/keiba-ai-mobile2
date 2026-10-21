"""Outcome-free adapters and exact B0-B4 research transformations."""
import math
import re
from statistics import mean, stdev
from .prediction_table_ui import number, horse_key
from .candidate_profile import facts

TRANSFORM_VERSION='research_b_transform_20261021_v1'
SETS={
 'B1':['ability_z','jockey_signal'],
 'B2':['ability_z','jockey_signal','class_signal'],
 'B3_JRA':['ability_z','jockey_signal','class_signal','weight_signal','long_layoff_70','long_layoff_180','train_signal','low_train_layoff'],
 'B3_NAR':['ability_z','jockey_signal','class_signal','weight_signal','long_layoff_70','long_layoff_180','body_signal'],
 'B4_JRA':['ability_z','jockey_signal','class_signal','weight_signal','long_layoff_70','long_layoff_180','train_signal','low_train_layoff','venue_good_feature','exact_good_feature','age3_mixed'],
 'B4_NAR':['ability_z','jockey_signal','class_signal','weight_signal','long_layoff_70','long_layoff_180','body_signal','venue_good_feature','exact_good_feature'],
 'SELECTED_JRA':['ability_z','jockey_signal','train_signal','low_train_layoff','long_layoff_70','long_layoff_180','weight_signal'],
 'SELECTED_NAR':['ability_z','jockey_signal','venue_good_feature','exact_good_feature'],
}
RAW_FIELDS=('no','ability','jockey_p','jockey_n','daygap','weightdiff','gr','class_delta','bodydiff','age3','venue_good','exact_good')

def finite(v):
    if isinstance(v,bool):return None
    n=number(v)
    return n if n is not None and math.isfinite(n) else None

def first(row,*keys):
    return next((row[k] for k in keys if finite(row.get(k)) is not None),None)

def extract(result):
    rows=result.overall_table.to_dict('records') if result.overall_table is not None else []
    info=result.race_info or {};out=[]
    for row in rows:
        no=horse_key(row)
        p=facts(row,info);conditions=p['condition_facts']['conditions']
        def good(key):
            state=conditions[key]['state']
            return True if state=='placed' else False if state in ('started','absent') else None
        grade=str(row.get('調教評価') or row.get('training_market') or '')
        match=re.match(r'\s*([ABCD])\b',grade)
        age=str(row.get('性齢') or row.get('sex_age') or '')
        # Target race outcomes and corner-derived score/rank fields are not read.
        out.append(dict(no=no,ability=finite(first(row,'_ver3_ability_core','ver3_ability_core')),
          jockey_p=finite(first(row,'_jockey_course_place_rate','jockey_course_top3_rate')),
          jockey_n=finite(first(row,'_jockey_course_starts','jockey_course_runs')),
          daygap=finite(row.get('_days_since_last')),weightdiff=finite(row.get('_load_weight_change')),
          gr=match[1] if match else None,class_delta=None,bodydiff=finite(row.get('_body_weight_change')),
          age3=bool(re.search(r'3$',age)) if age else None,
          venue_good=good('venue'),exact_good=good('venue_distance'),
          evidence=dict(past_runs=p['runs'],conditions=conditions,source='saved_prediction_overall_table',timing_status='capture_time_unverified')))
    return out

def transform(rows):
    """pandas std(ddof=1), clipping and missing-neutral rules from source code."""
    ability=[finite(h.get('ability')) for h in rows]
    if not rows or any(v is None for v in ability):raise ValueError('全出走馬の純能力が必要です')
    avg=mean(ability);sd=stdev(ability) if len(ability)>1 else 0
    ages={h.get('age3') for h in rows if h.get('age3') is not None};mixed=len(ages)>1
    out=[]
    clip=lambda x,lo,hi:max(lo,min(hi,x))
    for h,ab in zip(rows,ability):
        p,n=finite(h.get('jockey_p')),finite(h.get('jockey_n'))
        jockey_known=p is not None and 0<=p<=100 and n is not None and n>=0 and n.is_integer()
        day,w,cls,body=(finite(h.get(k)) for k in ('daygap','weightdiff','class_delta','bodydiff'))
        gr=h.get('gr');missing=[k for k in RAW_FIELDS if k!='no' and h.get(k) is None]
        if not jockey_known:missing+=['jockey_signal']
        f=dict(ability_z=clip((ab-avg)/sd,-3,3) if sd else 0,
          jockey_signal=clip((p/100-.25)*n/(n+50)*4,-2,2) if jockey_known else 0,
          class_signal=(1 if cls>0 else -1 if cls<0 else 0) if cls is not None else 0,
          weight_signal=clip(w,-5,5)/3 if w is not None else 0,
          long_layoff_70=float(day>=70) if day is not None else 0,
          long_layoff_180=float(day>=180) if day is not None else 0,
          train_signal={'A':1,'B':.5,'C':-.5,'D':-1}.get(gr,0),
          low_train_layoff=float(gr in ('C','D') and day is not None and day>=70),
          body_signal=clip(body,-20,20)/10 if body is not None else 0,
          age3_mixed=float(bool(h.get('age3')) and mixed),
          venue_good_feature=float(h.get('venue_good') is True),exact_good_feature=float(h.get('exact_good') is True))
        out.append(dict(no=str(h['no']),features=f,missing=missing))
    return out
