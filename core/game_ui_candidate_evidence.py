"""Read-only evidence for marked-horse comparison, never scoring or persistence."""
from datetime import date
from .prediction_table_ui import number, text, pick
from .supplementary_assessment import KEY, style, position
from .jockey_positive import inputs, evaluate, identity

MARK_ORDER = {'◎': 0, '○': 1, '▲': 2, '✔': 3, '△': 4, '✓': 5, '☆': 6}


def normalized_mark(value):
    return text(value).replace('\ufe0e', '').replace('\ufe0f', '')


def candidates(view, label):
    def order(i):
        h = view[i]
        rank, score, no = number(h.get('rank')), number(h.get('score')), number(h.get('no'))
        return (MARK_ORDER[normalized_mark(h.get('mark'))],
                rank if rank is not None else float('inf'),
                -score if score is not None else float('inf'),
                no if no is not None else float('inf'), i)
    rows = sorted((i for i, h in enumerate(view)
                   if normalized_mark(h.get('mark')) in MARK_ORDER), key=order)
    return dict(key='final', label=label, kind='candidates', rows=rows, cards=[],
                eligible=len(rows), total=len(view),
                note='＋／−は参考材料です。横・縦にスクロールして全候補を確認できます。馬名を選ぶと根拠の全文を表示します。')


def verified_interval(row, info):
    """A dated actual start is required; cancellations and conflicting dates do not count."""
    def parsed(value):
        try: return date.fromisoformat(str(value).replace('/', '-'))
        except (ValueError, TypeError): return None
    today = parsed(pick(info, 'race_date', 'date', '開催日'))
    runs = row.get('_past_runs')
    starts, uncertain = [], []
    for run in runs if isinstance(runs, (list, tuple)) else []:
        if not isinstance(run, dict): continue
        day = parsed(run.get('race_date'))
        status = text(run.get('position'))
        if any(x in status for x in ('取消', '除外')): continue
        if day is None:
            uncertain.append(None)
            continue
        if not today or day >= today: continue
        n = number(status)
        if (n is not None and n > 0 and n.is_integer()) or status in ('中止', '失格'):
            starts.append(day)
        else: uncertain.append(day)
    latest = max(starts) if starts else None
    days = (today-latest).days if today and latest else None
    if latest and any(d is None or d > latest for d in uncertain): days = None
    saved = number(pick(row, '_days_since_last', 'レース間隔日数', 'rest_days'))
    conflict = days is not None and saved is not None and days != saved
    return dict(days=None if conflict else days,
                last_start=latest.isoformat() if latest else None,
                race_date=today.isoformat() if today else None,
                status='conflict' if conflict else 'verified' if days is not None else 'unknown')


def weight_pair(row):
    current = number(pick(row, '_display_current_load_weight', '_current_load_weight', '斤量', 'weight'))
    previous = number(pick(row, '_display_previous_load_weight', '_previous_load_weight', '前走斤量', 'previous_load_weight'))
    delta = current-previous if current is not None and previous is not None and current > 0 and previous > 0 else None
    saved = number(pick(row, 'weight_change_market', '_display_load_weight_change', '_load_weight_change', '斤量増減'))
    if delta is not None and saved is not None and abs(delta-saved) > .0001: delta = None
    return dict(current=current, previous=previous, delta=delta)


def evidence(horse, row, race_info):
    """Use only pre-race inputs and existing adjudication; missing facts remain neutral."""
    plus, minus, neutral, audit = [], [], [], {}
    for key, label in [('ability', '純能力'), ('course', 'コース'), ('distance', '距離'),
                       ('star', '★'), ('away', '☆'), ('average', '3走平均')]:
        metric = dict(value=horse.get('ability'), rank=horse.get('ability_rank')) if key == 'ability' else horse.get(key, {})
        value, rank = number(metric.get('value')), number(metric.get('rank'))
        if value is not None and rank is not None and rank.is_integer() and 1 <= rank <= 3:
            plus.append(f'{label}{int(rank)}位')
            audit[key] = dict(value=value, rank=int(rank), source='existing_full_field_display_index')

    a = row.get(KEY) or {}
    pace = a.get('pace')
    s, pos, corner = style(row), position(row), horse.get('corner')
    facts = '／'.join(x for x in [f'{pace}想定' if pace in ('S','M','H') else '',
                                 f'{s}脚質' if s in ('逃','先','差','追') else '',
                                 f'4角{corner}番手' if corner is not None else pos] if x)
    reason = text(a.get('development_reason'))
    if a.get('development') == '◎' and reason:
        plus.append('展開有利（条件付き）：'+facts)
        audit['development'] = dict(source=KEY, reason=reason, facts=facts)
    else:
        # Old H/S-only judgments lack full context. Reuse provider judgments only
        # with explicit course tendency plus known style, pace and current position.
        mark = text(row.get('course_development_mark'))
        reason = text(row.get('course_development_reason'))
        bias = text(pick(row, '_favorable_position_label', 'favorable_position_label_market'))
        supported = pace in ('S','M','H') and s in ('逃','先','差','追') and bool(pos) and any(x in bias for x in ('前有利','後有利'))
        if supported and reason and mark in ('○','△','－'):
            (plus if mark == '○' else minus).append('展開：'+reason+'（'+facts+'）')
            audit['development'] = dict(source='course_development_mark/reason', reason=reason, facts=facts, bias=bias)
        elif facts: neutral.append('位置・脚質の参考：'+facts)

    weights = weight_pair(row)
    audit['weight'] = weights
    delta = weights['delta']
    if delta is not None and delta < 0: plus.append(f'斤量−{abs(delta):.1f}kg')
    if delta is not None and delta >= 2: minus.append(f'斤量＋{delta:.1f}kg')

    interval = verified_interval(row, race_info or {})
    audit['rest'] = interval
    days = interval['days']
    if days is not None and days >= 90: minus.append(('長期休養' if days >= 180 else '休養')+str(days)+'日')
    if horse['mode'] == 'jra':
        grade = horse.get('training')
        if grade == 'A': plus.append('調教A')
        elif grade in ('C','D'): minus.append('調教'+grade)

    # Reuse the established jockey_positive thresholds, on copied facts only.
    facts_j = inputs(row)
    invalid = ('', '—', '-', '未取得', '不明')
    for key in ('current_jockey_name', 'previous_jockey_name'):
        if facts_j[key] in invalid and text(row.get(key)) not in invalid:
            facts_j[key] = text(row[key])
    judged = evaluate(facts_j, horse['mode'])
    current, previous = facts_j['current_jockey_name'], facts_j['previous_jockey_name']
    named = current not in invalid
    same_condition = (row.get('jockey_previous_source') == 'same_race_saved_same_condition_exact_identity'
                      or (text(row.get('previous_jockey_stat_condition')) == facts_j['jockey_stat_condition']
                          and bool(facts_j['jockey_stat_condition'])))
    upgrade = (judged['jockey_upgrade_positive'] and named and previous not in invalid
               and identity(current) != identity(previous) and same_condition)
    if upgrade: plus.append(f'騎手強化（複勝率＋{judged["jockey_place_rate_delta"]:g}pt）')
    elif judged['jockey_absolute_positive'] and named: plus.append('騎手実績良好')
    audit['jockey'] = dict(facts_j, absolute=bool(judged['jockey_absolute_positive'] and named),
                           upgrade=bool(upgrade), negative='未評価（検証済み低下判定なし）')
    return dict(plus=list(dict.fromkeys(plus)), minus=list(dict.fromkeys(minus)),
                neutral=neutral, audit=audit)
