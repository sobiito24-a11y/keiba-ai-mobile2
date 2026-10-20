"""NAR-only, fresh-prediction F2 selection. No DB, network, results or fitting."""
import copy
from datetime import datetime, timezone, timedelta
from .nar_top5_order import horse_no, number, result_rows
from .course_stats_parser import parse

VERSION = 'nar_f2_actual_course_v1_20261020'
POLICY = 'f2_priority'  # explicit rollback: legacy
CONFIG = dict(prior=.25, prior_n=40, scale=20, corner=2)
MARKS = {1:'◎',2:'○',3:'▲',4:'✔︎',5:'△'}


class HTMLSource:
    def __init__(self, text, name):
        self.raw=text.encode('utf-8'); self.name=name
    def read_bytes(self):return self.raw
    def __str__(self):return self.name


def inputs(rows, html_files, info):
    stats={};issues=[]
    for kind in ('jockey','style'):
        try:
            text=html_files.get(kind)
            if not text:raise ValueError('missing_html')
            values,links,errors=parse(HTMLSource(text,kind+'.html'))
            if not values or errors:raise ValueError('invalid_statistics')
            first=values[0]
            if (first['authority']!='NAR' or first['kind']!=kind
                or first['venue']!=info.get('venue') or first['distance']!=number(info.get('distance'))
                or first['surface']!=str(info.get('surface')).replace('ダート','ダ')):
                raise ValueError('course_identity_mismatch')
            by={x['stat_id']:x for x in values}
            horses={horse_no(h):str(h.get('馬名',h.get('horse_name',''))) for h in rows}
            if len(links)!=len(horses) or {str(x['horse_no']):x['horse_name'] for x in links}!=horses:
                raise ValueError('runner_identity_mismatch')
            for link in links:
                if link['race_id']!=str(info.get('race_id')):raise ValueError('race_identity_mismatch')
            for link in links:
                value=by[link['stat_id']]
                stats[(str(link['horse_no']),kind)]={k:value[k] for k in ('starts','top3','wins','second','third','entity_label','period_raw','period_start','period_end','source_sha256','source_url','captured_at','as_of_status')}
        except (ValueError,KeyError,TypeError) as exc:
            issues.append(kind+':'+str(exc))
    return stats,issues


def evaluate(rows, legacy, stats, issues=()):
    """Fixed coefficients identical to NAR_P_F2; all-runner availability gate."""
    old={str(h['horse_no']):h for h in legacy['horses']};evaluated=[];n=len(rows)
    for row in rows:
        no=horse_no(row);base=next((number(row.get(k)) for k in ('market_ability_score','能力評価値','ability_display_score') if number(row.get(k)) is not None),None)
        missing=[];contributions={};evidence={}
        if base is None:missing.append('ability_missing')
        for kind in ('jockey','style'):
            st=stats.get((no,kind));evidence[kind]=st;delta=None
            if st and st['starts']>0 and 0<=st['top3']<=st['starts']:
                delta=CONFIG['scale']*((st['top3']+CONFIG['prior_n']*CONFIG['prior'])/(st['starts']+CONFIG['prior_n'])-CONFIG['prior'])
            else:missing.append(kind+(':no_sample' if st else ':unavailable'))
            contributions[kind]=delta
        corner=number(row.get('netkeiba_corner4_rank'));group=None
        if corner is not None and 1<=corner<=n:
            u=(corner-.5)/n;group='先団' if u<1/3 else '中団' if u<2/3 else '後方'
            contributions['corner']={'先団':2,'中団':0,'後方':-2}[group]
        else:contributions['corner']=None;missing.append('corner_missing')
        evaluated.append(dict(horse_no=no,ability=base,corner=corner,corner_group=group,
            contributions=contributions,evidence=evidence,missing=missing,
            score=((base+contributions['jockey'])+contributions['style'])+contributions['corner'] if not missing else None,rank=None))
    complete=bool(rows) and len(old)==len(rows) and all(h['score'] is not None for h in evaluated)
    if complete:
        for rank,h in enumerate(sorted(evaluated,key=lambda h:(-h['score'],number(old[h['horse_no']].get('nar_final_rank')) or float('inf'),int(h['horse_no']))),1):h['rank']=rank
    active=complete and POLICY=='f2_priority'
    result=copy.deepcopy(legacy);result['legacy_comparison']=copy.deepcopy(legacy)
    result['f2_audit']=dict(version=VERSION,policy=POLICY,config=CONFIG,complete=complete,
        selected_model=VERSION if active else legacy['model_version'],
        fallback_reasons=[] if active else (['policy_legacy'] if POLICY=='legacy' else list(issues)+sorted({m for h in evaluated for m in h['missing']})),
        evaluated_at=datetime.now(timezone(timedelta(hours=9))).isoformat(),
        temporal_status='capture_time_unverified',long_term_improvement_proven=False,
        adoption_basis='exploratory_61R_Top5_54_to_55_podium_139_to_148_Top1_21_to_20',horses=evaluated)
    by={h['horse_no']:h for h in evaluated}
    if active:
        result['model_version']=VERSION;result['coefficients']=CONFIG.copy();result['provenance']='new_prediction_actual_html_counts'
    for h in result['horses']:
        no=str(h['horse_no']);v=by[no]
        h['nar_original_pure_top5_group']=h.get('pure_ability_top5_group',False)
        h['nar_f2_score']=v['score'];h['nar_f2_version']=VERSION
        if active:
            # Compatibility alias consumed by existing display adapters; original membership saved above.
            h.update(pure_ability_top5_group=v['rank']<=5,nar_final_rank=v['rank'],nar_final_mark=MARKS.get(v['rank'],''),
                nar_top5_order_score=v['score'],nar_top5_order_version=VERSION,nar_top5_order_status='f2_actual_course',
                nar_top5_order_rank_change=(h['pure_ability_rank']-v['rank']) if h.get('pure_ability_rank') is not None else None)
        elif v['ability'] is None or v['corner'] is None or not 1<=v['corner']<=n:
            h.update(nar_final_rank=None,nar_final_mark='',pure_ability_top5_group=False,nar_top5_order_score=None,nar_top5_order_status='undetermined_missing_legacy_input')
        h['nar_formal_top5_member']=bool(h['pure_ability_top5_group'])
    result['final_group']=[str(h['horse_no']) for h in sorted(result['horses'],key=lambda h:number(h.get('nar_final_rank')) or float('inf')) if h['pure_ability_top5_group']]
    result['pure_ability_top5_group']=list(legacy.get('pure_ability_top5_group',[]))
    return result


def attach_new(result,html_files):
    if result.race_mode!='nar':return result
    from .nar_top5_order import snapshot
    legacy=snapshot(result)
    if 'f2_audit' in legacy:return result
    from .prediction_history import _race_info
    rows=result_rows(result);info=_race_info(result);stats,issues=inputs(rows,html_files,info)
    payload=evaluate(rows,legacy,stats,issues)
    result.debug_info=dict(result.debug_info or {},nar_top5_corner_order=payload)
    # Fresh predictions only: all consumers and serialized display marks see the same order.
    from .nar_check_selection import select
    from .nar_display_mark import display_mark
    by={str(h['horse_no']):h for h in payload['horses']}
    checked=select([dict(row,**by[horse_no(row)]) for row in rows],rows)
    values={horse_no(row):row for row in checked}
    from .nar_top5_order import FIELDS
    for attribute in ('overall_table','horse_evaluation'):
        table=getattr(result,attribute,None)
        if table is None or table.empty:continue
        updated=[]
        for row in table.to_dict('records'):
            source=values.get(horse_no(row))
            if source:
                row.update({k:source.get(k) for k in FIELDS})
                row.update({k:v for k,v in source.items() if k.startswith('nar_check_') or k=='nar_submark'})
                row['表示印']=display_mark(source)
            updated.append(row)
        import pandas as pd
        setattr(result,attribute,pd.DataFrame(updated))
    return result
