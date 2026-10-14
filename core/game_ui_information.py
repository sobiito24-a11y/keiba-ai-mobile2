"""Read-only information tabs, using already saved material and change facts."""
from .prediction_table_ui import number, pick, text


def reasons(value):
    if text(value) in ('', '—', '未計算', '未取得'):
        return []
    return list(dict.fromkeys(x.strip() for x in text(value).split(' / ') if x.strip()))


def changes(row):
    from .market_compare import _weight
    from .jockey_positive import inputs
    delta = number(pick(row, 'weight_change_market', '_display_load_weight_change',
                        '_load_weight_change', '斤量増減', 'weight_change'))
    if delta is None:
        delta = _weight(row)[1]
    facts = inputs(row)
    status = facts['jockey_change_status']
    current, previous = facts['current_jockey_name'], facts['previous_jockey_name']
    # A placeholder is not a rider identity. Keep explicit saved change facts,
    # but never infer a replacement by comparing a name with "未取得".
    if current in ('', '未取得', '—') or previous in ('未取得', '—'):
        explicit = text(pick(row, 'jockey_change_status', 'jockey_change_market',
                             '騎手継続/乗替', 'jockey_change', '_display_jockey_changed',
                             '_jockey_changed', 'jockey_changed'))
        status = '乗替' if explicit in ('乗替', '乗り替わり', 'True', 'true', '1') else '未取得'
    jockey = ('乗替 '+previous+' → '+current if previous and previous not in ('未取得','—') and current and current not in ('未取得','—')
              else '乗替') if status == '乗替' else '継続' if status == '継続' else '—'
    return dict(weight_delta=delta, jockey_changed=status == '乗替', jockey_change_text=jockey)


def information(view, key, label):
    pool = [h for h in view if (reasons(h.get('plus')) or reasons(h.get('caution')))] if key == 'materials' else [
                h for h in view if h.get('jockey_changed') is True or
                (h.get('weight_delta') is not None and h['weight_delta'] != 0)]
    pool.sort(key=lambda h: number(h['no']) if number(h['no']) is not None else float('inf'))
    return dict(key=key, label=label, kind='information', eligible=len(pool), total=len(view),
                cards=[], rows=[next(i for i,x in enumerate(view) if x['no']==h['no']) for h in pool], note='')
