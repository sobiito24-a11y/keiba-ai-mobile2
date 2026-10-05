"""Final JRA roles over frozen scores; no five-horse limit on marked horses."""
import math
import re
import unicodedata

from .jra_display_mark import jra_base_display_mark_from_row, jra_display_mark_from_row


def number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def horse_key(row):
    for field in ('number', '馬番', '馬', 'horse_no'):
        value = number(row.get(field))
        if value is not None and value.is_integer():
            return str(int(value))
    return ''


def final_mark_sort_key(row):
    mark = jra_display_mark_from_row(row).replace('\ufe0e', '').replace('\ufe0f', '')
    rank = number(row.get('_display_jra_top5_rank', row.get('jra_top5_rank')))
    score = number(row.get('_display_jra_top5_score', row.get('jra_top5_score')))
    return ({'◎': 0, '○': 1, '▲': 2, '✔': 3, '△': 4, '✓': 5, '☆': 6}.get(mark, 7),
            rank if rank is not None and rank > 0 else math.inf,
            -score if score is not None else math.inf)


def training_grade(row):
    for field in ('jra_training_grade', 'training_grade', 'training_market', '調教評価', '調教', 'training'):
        raw = unicodedata.normalize('NFKC', str(row.get(field, '')))
        match = re.match(r'\s*([ABCD])(?:\b|[/／・\s]|$)', raw)
        if match:
            return match[1]
    return None


def apply_final_marks(result, rows):
    """Annotate copies and allocate main roles only within the formal Top5.

    Only >=70 days AND training C/D caps a main role at △. Slow/back and
    weight increases remain warnings pending further validation. Missing inputs
    never constitute a negative. Outcome fields, odds and shadow ranks are unused.
    """
    from .jra_practical_inputs import practical_inputs
    from .jra_purchase_navigator import _saved_interval_days
    from types import SimpleNamespace
    source_result = SimpleNamespace(race_mode='jra',
        race_info=getattr(result, 'race_info', {}) or {},
        horse_evaluation=getattr(result, 'horse_evaluation', None),
        overall_table=getattr(result, 'overall_table', None),
        debug_info=getattr(result, 'debug_info', {}) or {},
        created_at=getattr(result, 'created_at', ''),
        source_files=getattr(result, 'source_files', {}))
    data = practical_inputs(source_result)
    inputs = {str(h['horse_no']): h for h in data.get('horses', [])}
    indexes = {horse_key(h): h for h in (result.overall_table.to_dict('records')
               if result.overall_table is not None else [])}
    out = []
    for row in rows:
        h = dict(row)
        source = dict(indexes.get(horse_key(row), {}))
        source.update(row)
        evidence = inputs.get(horse_key(row), {})
        grade = evidence.get('training_grade') or training_grade(source)
        days = evidence.get('rest_days')
        if days is None:
            days = _saved_interval_days(source, source_result.race_info)
        reasons = []
        capped = days is not None and days >= 70 and grade in ('C', 'D')
        if capped:
            reasons.append(f'休養{days:g}日＋調教{grade}：上位印対象外（最大△）')
        corner = number(evidence.get('corner4_rank'))
        if data.get('pace') == 'S' and corner is not None and corner >= 9:
            reasons.append(f'スロー想定×4角{corner:g}番手（注意・強制降格なし）')
        load = number(evidence.get('load_change'))
        if load is not None and load >= 2:
            reasons.append(f'斤量前走比＋{load:g}kg（注意・強制降格なし）')
        h['_display_jra_final_mark'] = jra_base_display_mark_from_row(h)
        formal_rank = number(h.get('_display_jra_top5_rank'))
        if formal_rank is not None and formal_rank > 3 and h['_display_jra_final_mark'] in ('◎', '○', '▲'):
            h['_display_jra_final_mark'] = '△'
        h['_display_jra_mark_cap'] = bool(capped)
        h['_display_jra_mark_reasons'] = reasons
        h['_display_jra_mark_policy'] = 'jra_final_mark_v1'
        out.append(h)
    # Preserve existing roles unless there is an actual capped main candidate.
    top = sorted([h for h in out if number(h.get('_display_jra_top5_rank')) in (1, 2, 3, 4, 5)],
                 key=lambda h: number(h['_display_jra_top5_rank']))
    if any(h['_display_jra_mark_cap'] and h['_display_jra_final_mark'] in ('◎', '○', '▲') for h in top):
        safe = [h for h in top if not h['_display_jra_mark_cap']]
        for mark, h in zip(('◎', '○', '▲'), safe):
            h['_display_jra_final_mark'] = mark
    for h in out:
        if h['_display_jra_mark_cap'] and h['_display_jra_final_mark'] in ('◎', '○', '▲', '✔', '✔︎'):
            h['_display_jra_final_mark'] = '△'
    return sorted(out, key=final_mark_sort_key)
