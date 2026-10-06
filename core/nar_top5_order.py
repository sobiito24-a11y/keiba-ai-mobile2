"""NAR protected ability group, independently ordered by exact corner-four input."""
import copy
import math
from datetime import datetime, timezone
from .nar_ability_rank import canonical_nar_ability_rank

MODEL_VERSION = "nar_top5_corner_order_v1_20261006"
ABILITY_COEF = 0.01180085
CORNER4_COEF = -0.22088414
FIELDS = ('pure_ability_top5_group', 'nar_final_rank', 'nar_final_mark',
          'nar_top5_order_score', 'nar_top5_order_version', 'nar_top5_order_status',
          'nar_top5_order_pure', 'nar_top5_order_corner4', 'nar_top5_order_rank_change')

def number(value):
    if isinstance(value, bool): return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError): return None

def horse_no(row):
    for k in ('number', 'horse_no', '馬番', '馬'):
        n = number(row.get(k))
        if n is not None and n > 0 and n.is_integer(): return str(int(n))
    return ''

def sort_key(row):
    return (number(row.get('nar_final_rank')) or math.inf,
            canonical_nar_ability_rank(row) or math.inf,
            int(horse_no(row) or 999))

def annotate(rows):
    """Copy inputs; protect every saved rank <=5, including boundary ties.

    Missing core/corner fixes its original ordinal slot. Remaining eligible
    members occupy only the remaining slots. No median or score imputation.
    No ability rank is inferred from a rounded score.
    """
    out = [dict(r) for r in rows]
    keys = [horse_no(r) for r in out]
    valid = all(keys) and len(set(keys)) == len(keys)
    ordered = sorted(out, key=lambda r:(canonical_nar_ability_rank(r) or math.inf, int(horse_no(r) or 999)))
    group = [r for r in ordered if canonical_nar_ability_rank(r) is not None and canonical_nar_ability_rank(r)<=5]
    for r in out:
        pure = number(r.get('ver3_ability_core'))
        corner = number(r.get('netkeiba_corner4_rank'))
        if corner is not None and (corner<1 or not corner.is_integer()): corner=None
        member = valid and r in group
        r.update(pure_ability_top5_group=member, nar_final_rank=None, nar_final_mark='',
                 nar_top5_order_score=ABILITY_COEF*pure+CORNER4_COEF*corner if member and pure is not None and corner is not None else None,
                 nar_top5_order_version=MODEL_VERSION,nar_top5_order_pure=pure,nar_top5_order_corner4=corner,
                 nar_top5_order_status='invalid_horse_keys' if not valid else 'outside_group' if not member else 'ordered' if pure is not None and corner is not None else 'missing_input_position_protected',nar_top5_order_rank_change=None)
    if not valid: return out
    movable = sorted([r for r in group if r['nar_top5_order_score'] is not None],key=lambda r:(-r['nar_top5_order_score'],canonical_nar_ability_rank(r),int(horse_no(r))))
    iterator = iter(movable)
    final = [next(iterator) if r['nar_top5_order_score'] is not None else r for r in group]
    final += [r for r in ordered if r not in group]
    for i,r in enumerate(final,1):
        rank=canonical_nar_ability_rank(r)
        r['nar_final_rank']=i if rank is not None else None
        r['nar_top5_order_rank_change']=rank-i if rank is not None else None
        if r['pure_ability_top5_group']: r['nar_final_mark']={1:'◎',2:'○',3:'▲',4:'✔︎'}.get(i,'△')
    return out

def result_rows(result):
    """Join factual inputs by horse number. Saved audits take precedence."""
    overall=result.overall_table.to_dict('records') if result.overall_table is not None else []
    evaluation=result.horse_evaluation.to_dict('records') if result.horse_evaluation is not None else []
    by={horse_no(r):dict(r) for r in overall}
    for row in evaluation:
        key=horse_no(row); merged=by.setdefault(key,{})
        for k,v in row.items():
            if v is not None and not (isinstance(v,float) and math.isnan(v)): merged[k]=v
    return list(by.values())

def snapshot(result):
    if result.race_mode!='nar': return None
    saved=(getattr(result, 'debug_info', None) or {}).get('nar_top5_corner_order')
    if isinstance(saved,dict): return copy.deepcopy(saved)
    rows=annotate(result_rows(result))
    return dict(model_version=MODEL_VERSION,evaluated_at=datetime.now(timezone.utc).isoformat(),
                provenance='derived_from_saved_inputs',race_id=(result.race_info or {}).get('race_id'),
                coefficients=dict(ability=ABILITY_COEF,corner4=CORNER4_COEF),
                pure_ability_top5_group=[horse_no(r) for r in rows if r['pure_ability_top5_group']],
                final_group=[horse_no(r) for r in sorted(rows,key=sort_key) if r['pure_ability_top5_group']],
                horses=[dict(horse_no=horse_no(r),pure_ability_rank=canonical_nar_ability_rank(r),actual_finish=None,**{k:r[k] for k in FIELDS}) for r in rows])

def attach(result):
    if result.race_mode=='nar':
        payload=snapshot(result)
        result.debug_info=dict(result.debug_info or {},nar_top5_corner_order=payload)
    return result

def comparison_fields(rows, source_rows):
    """Only new final fields and derived display aliases; no source mutation."""
    source_rows=list(source_rows)
    if source_rows and all(r.get('nar_top5_order_version') and 'nar_final_mark' in r for r in source_rows):
        by={horse_no(r):r for r in source_rows}
    else:
        by={horse_no(r):r for r in annotate(source_rows)}
    for row in rows:
        extra=by.get(horse_no(row),{})
        row.update({k:extra.get(k) for k in FIELDS})
        row['nar_top5_rank']=extra.get('nar_final_rank')
        from .nar_display_mark import formal_mark, submark
        row['nar_final_mark']=formal_mark(row)
        row['nar_submark']=submark(extra) or submark(row)
        row['nar_top5_mark']=row['nar_final_mark']
        row['nar_top5_role']={'◎':'中心','○':'本線','▲':'本線','✔︎':'狙い','△':'押さえ'}.get(row['nar_top5_mark'],'')
        row['nar_top5_reason']='純能力Top5圏を保護し、圏内だけ能力＋4角で再順位'
    return rows


def overlay_saved(result, rows):
    payload=(getattr(result, 'debug_info', None) or {}).get('nar_top5_corner_order')
    if not isinstance(payload,dict): return rows
    by={str(h['horse_no']):h for h in payload.get('horses',[])}
    return [dict(r, **{k:by[horse_no(r)].get(k) for k in FIELDS}) if horse_no(r) in by else dict(r) for r in rows]


def validation_rows(payload, finishes=None):
    """Results joined only for audit, never used by ranking."""
    finishes=finishes or {}
    return [dict(h, race_id=payload.get('race_id'),actual_finish=finishes.get(str(h['horse_no']))) for h in payload.get('horses',[])]
