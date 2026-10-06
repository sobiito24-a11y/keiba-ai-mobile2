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
    if 'nar_check_selected' in row:
        return '✓' if row['nar_check_selected'] else ''
    # A single row cannot establish the race-wide selection/cap.
    return ''

def display_mark(row):
    return formal_mark(row) or submark(row)

def summary_rows(rows):
    return [r for r in rows if display_mark(r)]
