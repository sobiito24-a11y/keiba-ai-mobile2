"""Unadopted layoff candidates, isolated from fresh predictions and snapshots.

The additional 18-race cohort lost 5.56 points of full Top5 podium capture.
Therefore production remains A; this module is only a reproducible comparison.
"""
from copy import deepcopy
from datetime import date
import math

VERSION = 'jra_layoff_research_v1_20261014'


def rest_evidence(row, race_info):
    """Only a dated actual start proves the interval; conflicts/unknowns stay unknown."""
    def parsed(value):
        try:return date.fromisoformat(str(value))
        except (ValueError, TypeError):return None
    day = parsed(race_info.get('race_date') or race_info.get('date'))
    starts, unknown = [], []
    runs = row.get('_past_runs')
    for run in runs if isinstance(runs, (list, tuple)) else []:
        if not isinstance(run, dict):continue
        d = parsed(run.get('race_date'))
        status = str(run.get('position', '')).strip()
        if not day or not d or d >= day:continue
        if '取消' in status or '除外' in status:continue
        if (status.isdigit() and int(status)>0) or status in ('中止', '失格'):starts.append(d)
        else:unknown.append(d)
    latest = max(starts) if starts else None
    days = (day-latest).days if latest and not any(d>latest for d in unknown) else None
    saved = row.get('_days_since_last')
    conflict = not isinstance(saved,bool) and isinstance(saved,(int,float)) and math.isfinite(saved) and days is not None and saved != days
    return dict(days=None if conflict else days, last_start=latest.isoformat() if latest else None,
                race_date=day.isoformat() if day else None,
                status='conflict' if conflict else 'verified' if days is not None else 'unknown')


def restrict_honmei(rows):
    """Reallocate roles within formal Top5 only; score ranks remain untouched."""
    top=sorted([h for h in rows if 1 <= (h.get('jra_top5_rank') or 999) <= 5],key=lambda h:h['jra_top5_rank'])
    if not any(h.get('jra_layoff_honmei_cap') and h['_display_jra_final_mark']=='◎' for h in top):return
    safe=[h for h in top if not h['_display_jra_mark_cap']]
    lead=next((h for h in safe if not h.get('jra_layoff_honmei_cap')),None)
    others=[h for h in safe if h is not lead]
    if lead:lead['_display_jra_final_mark']='◎'
    # Main roles follow the established score order after the eligible leader.
    for i,h in enumerate(others):
        if i < 2:h['_display_jra_final_mark']=('○','▲')[i]
        elif h['_display_jra_final_mark'] in ('◎','○','▲'):h['_display_jra_final_mark']='△'


def evaluate_candidate(result, comparison, model='C'):
    """Return a separate research object; never modify PredictionResult or inputs."""
    from .jra_final_mark import horse_key, apply_final_marks
    from .v1_logic import (assign_jra_top5_scores_and_marks, jra_top5_sort_key,
                           jra_final_role_for_rank, final_mark_for_rank, jra_top5_reason)
    from .position_signals import is_jump_race
    if result.race_mode != 'jra' or is_jump_race(result.race_info or {}):
        raise ValueError('長期休養の比較対象はJRA平地のみです')
    if model not in ('A','B','C'):raise ValueError('比較方式はA/B/Cです')
    comparison=deepcopy(comparison)
    sources={horse_key(h):h for h in result.overall_table.to_dict('records')} if result.overall_table is not None else {}
    evidence={horse_key(h):rest_evidence(sources.get(horse_key(h),{}),result.race_info or {}) for h in comparison.get('rows',[])}
    rows=comparison.get('rows',[])
    assign_jra_top5_scores_and_marks(rows,result.race_info or {},position_scoring=False)
    for h in rows:
        h['jra_layoff_evidence']=evidence[horse_key(h)]
        days=evidence[horse_key(h)]['days']
        penalty=-2.0 if model!='A' and days is not None and days>=180 else 0.0
        h.update(jra_layoff_days=days,jra_layoff_bonus=penalty,
                 jra_layoff_honmei_cap=model=='C' and penalty<0)
        h['jra_top5_score']=round(h['jra_top5_score']+penalty,3)
        for field in ('v1_score','v1_base_score','v1_final_score'):h[field]=h['jra_top5_score']
    rows.sort(key=jra_top5_sort_key)
    for rank,h in enumerate(rows,1):
        for field in ('jra_top5_rank','v1_final_rank','v1_base_rank'):h[field]=rank
        h['v1_final_role']=jra_final_role_for_rank(h,rank)
        h['v1_final_mark']=h['v1_mark']=final_mark_for_rank(rank,h['v1_final_role']) if rank<=5 else ''
        h['v1_final_reason']=jra_top5_reason(h)
        h['_display_jra_top5_rank']=h['jra_top5_rank'];h['_display_jra_top5_score']=h['jra_top5_score']
    marked=apply_final_marks(result,rows)
    if model=='C':restrict_honmei(marked)
    by={horse_key(h):h for h in marked}
    for h in rows:
        final=by[horse_key(h)]
        h['research_final_mark']=final['_display_jra_final_mark']
        h['research_mark_reasons']=final['_display_jra_mark_reasons']
        if h.get('jra_layoff_honmei_cap'):h['research_mark_reasons'].append('長期休養：◎対象外（最大○・未採用案）')
    comparison['rows']=sorted(rows,key=lambda h:h['jra_top5_rank'])
    return dict(rows=comparison['rows'],research_only=True,candidate_version=VERSION,
                model=model,baseline_score_version='jra_nonposition_v1_20261014',
                adopted=False,position_scoring=False)
