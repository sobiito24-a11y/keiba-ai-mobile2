"""NAR-only fixed evidence protocol; no odds, official scores or marks modified."""
import copy
import math
from .material_evidence_inputs import num
VERSION = "nar_material_reconsideration_research_v1"

def evaluate_nar_materials(data, *, include_base=True):
 out=copy.deepcopy(data);N=len(out['horses'])
 for h in out['horses']:
  positive={};negative={};missing=[]
  rank=h['ability_rank']
  if include_base and rank is not None and rank<=3:positive['ability']=f'保存純能力{rank}位'
  if rank is None:missing.append('純能力順位')
  cond=[k for k in ('distance','course','star','away') if h[k+'_rank'] is not None and h[k+'_rank']<=3]
  labels={'distance':'距離','course':'コース','star':'★','away':'☆'}
  if len(cond)>=2:positive['condition']='条件上位：'+' / '.join(f'{labels[k]}{h[k+"_rank"]}位' for k in cond)
  for k in ('distance','course','star','away'):
   if h[k] is None:missing.append(k)
  if h['distance_rank'] is not None and h['course_rank'] is not None and h['distance_rank']>N/2 and h['course_rank']>N/2:
   negative['condition']='距離・コースとも全頭順位の下半分'
  runs=h['runs']
  if sum(num(r.get('finish')) is not None and 1<=r['finish']<=3 for r in runs)>=2:
   positive['recent']='近3走のうち2走以上3着以内'
  if len(runs)==3 and all(num(r.get('value')) is not None for r in runs) and num(runs[0].get('finish')) is not None:
   if runs[0]['finish']>=6 and all(r['value']-runs[0]['value']>=5 for r in runs[1:]):
    negative['recent']='前走6着以下かつ指数が2・3走前より各5点以上低下'
  else:missing.append('近走低下比較の情報不足')
  c=h['corner4'];pace=h['pace']
  if c is not None and float(c).is_integer() and 1<=c<=N and pace in ('S','M','H'):
   if c<=math.ceil(N/3) and pace in ('S','M'):positive['position']='前1/3の4角想定×S/Mペース'
   if c>math.ceil(N*2/3) and pace=='S':negative['position']='後ろ1/3の4角想定×Sペース'
  else:missing.append('netkeiba4角または予測ペース')
  rate=h['jockey_rate'];count=h['jockey_runs']
  if rate is not None and count is not None and count>=20 and 0<=rate<=100:
   if rate>=30:positive['jockey']=f'騎手コース複勝率{rate:g}%（{count:g}走）'
   if rate<=10:negative['jockey']=f'騎手コース複勝率{rate:g}%（{count:g}走）'
  else:missing.append('騎手コース成績20走以上')
  h.update(good='◎' if len(positive)>=2 else '○' if positive else '—',
           concern='⚠' if len(negative)>=2 else '△' if negative else '—',
           good_reasons=positive,concern_reasons=negative,missing=missing)
 official=[h for h in out['horses'] if h['ability_rank'] is not None and h['ability_rank']<=5]
 official.sort(key=lambda h:(h['ability_rank'],h['horse_no']))
 top=[h['horse_no'] for h in official];shadow=top[:];swap=None
 if len(top)==5 and all(h['ability_rank'] is not None for h in out['horses']):
  outside=[h for h in out['horses'] if h['ability_rank']>5 and h['good']=='◎' and h['concern']!='⚠']
  inside=[h for h in official if h['concern']=='⚠']
  outside.sort(key=lambda h:(h['ability_rank'],-h['ability'] if h['ability'] is not None else math.inf,int(h['horse_no'])))
  inside.sort(key=lambda h:(-h['ability_rank'],h['ability'] if h['ability'] is not None else math.inf,int(h['horse_no'])))
  if outside and inside:
   incoming,removed=outside[0],inside[0]
   shadow[shadow.index(removed['horse_no'])]=incoming['horse_no']
   swap={'added':incoming['horse_no'],'removed':removed['horse_no'],
         'positive':incoming['good_reasons'],'negative':removed['concern_reasons']}
 out.update(model_version=VERSION,official_top5=top,shadow_top5=shadow,reconsideration=swap,
            eligible_box=len(top)==5 and all(h['ability_rank'] is not None for h in out['horses']))
 return out
