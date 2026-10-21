"""Display-only prioritisation of existing JRA candidates. No prediction mutation."""
from .prediction_table_ui import number
from .game_ui_candidate_evidence import normalized_mark, MARK_ORDER

VERSION = 'jra_focus_display_v1'


def evidence_groups(h):
    """Group correlated index ranks; these groups are not proven independent effects."""
    a = (h.get('candidate_evidence') or {}).get('audit') or {}
    groups = []
    if any(k in a for k in ('ability', 'course', 'distance', 'star', 'away', 'average')):
        groups.append('能力・適性')
    if h.get('training') == 'A': groups.append('調教')
    j = a.get('jockey') or {}
    if j.get('absolute') or j.get('upgrade'): groups.append('騎手')
    if 'development' in a and any('展開有利' in x for x in (h.get('candidate_evidence') or {}).get('plus', [])):
        groups.append('展開')
    return groups


def purple(h):
    rank = number(h.get('rank'))
    return h.get('mode') == 'jra' and rank is not None and rank > 5 and normalized_mark(h.get('mark')) == '✔'


def focus_order(h):
    return (number(h.get('rank')) or float('inf'), -len(evidence_groups(h)), number(h.get('no')) or float('inf'))


def annotate(view):
    eligible = sorted((h for h in view if purple(h) and 6 <= number(h['rank']) <= 8), key=focus_order)
    selected = {str(h['no']) for h in eligible[:2]}
    for h in view:
        if h.get('mode') != 'jra': continue
        candidate = normalized_mark(h.get('mark')) in MARK_ORDER or h.get('additional_reference')
        if h.get('formal_member') or not candidate: continue
        h['focus_label'] = '注目' if str(h['no']) in selected else '参考'
        h['focus_version'] = VERSION
        h['focus_evidence_groups'] = evidence_groups(h)
        h['focus_reason'] = ('既存の追加✔候補のうち正式6〜8位を優先（最大2頭）' if h['focus_label'] == '注目'
                             else '既存候補を保持。重点表示の対象外（判定の取消・減点ではありません）')
    return view


def partition(view, rows):
    main=[i for i in rows if view[i].get('focus_label') != '参考']
    if any(view[i].get('mode')=='jra' for i in rows):
        main.sort(key=lambda i: (not view[i].get('formal_member',False), number(view[i].get('rank')) or float('inf'), number(view[i].get('no')) or float('inf')))
    return main, [i for i in rows if view[i].get('focus_label') == '参考']
