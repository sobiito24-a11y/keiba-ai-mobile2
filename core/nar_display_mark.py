"""NAR marks are a presentation over frozen group/order, not new selection."""
from .nar_top5_order import number

def formal_mark(row):
    if not row.get('pure_ability_top5_group'):
        return ''
    rank=number(row.get('nar_final_rank'))
    if rank is None or rank<1 or not rank.is_integer():return ''
    return {1:'◎',2:'○',3:'▲',4:'✔︎'}.get(int(rank),'△')

def submark(row):
    if row.get('pure_ability_top5_group'):return ''
    # Only saved submarks or the unchanged legacy warning flag. No new vote.
    for key in ('nar_submark','mark','baseline_ver3_final_mark','表示印','display_mark','印','最終印'):
        value=str(row.get(key)).strip() if row.get(key) is not None else ''
        if value in ('✓','☆','注目','注目馬','注意馬'):return value
    flag=row.get('nar_warning_candidate')
    if str(flag).strip().lower() in ('true','1','1.0'):return '✓'
    return ''

def display_mark(row):
    return formal_mark(row) or submark(row)

def summary_rows(rows):
    return [r for r in rows if display_mark(r)]
