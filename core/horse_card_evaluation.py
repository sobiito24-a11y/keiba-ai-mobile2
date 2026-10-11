"""Read-only card header: only existing official values, never rank inference."""
import math
from html import escape
from .jra_rank_display import official_jra_values
from .position_signals import corner4_rank


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def card_evaluation_fields(row, mode):
    if mode == 'jra':
        rank, score = official_jra_values(row)
        label, side_label = 'JRAスコア', '展開'
        # Read the existing formal development assessment, not a new pace rule.
        side = '○' if isinstance(row.get('v1_pace_eval'), str) and row['v1_pace_eval'] == '○' else ''
    elif mode == 'nar':
        rank, score = row.get('nar_final_rank'), row.get('nar_top5_order_score')
        label, side_label = 'NAR最終スコア', '4角想定'
        corner = corner4_rank(row)
        side = f'{corner}番手' if corner is not None else '—'
    else:
        return None
    rank, score = _number(rank), _number(score)
    rank_text = f'{int(rank)}位' if rank is not None and rank >= 1 and rank.is_integer() else '—'
    score_text = f'{score:.1f}' if score is not None else '—'
    return ((label, f'{score_text} / {rank_text}'), (side_label, side))


def card_evaluation_html(row, mode):
    fields = card_evaluation_fields(row, mode)
    if fields is None:
        return ''
    cells = ''.join(
        '<div style="min-width:0;padding:5px 4px;background:rgba(128,128,128,.08);border-radius:6px;">'
        + '<div style="font-size:10px;line-height:1.3;overflow-wrap:anywhere;">' + escape(label) + '</div>'
        + '<div style="font-size:12px;font-weight:600;line-height:1.5;overflow-wrap:anywhere;min-height:1.5em;">'
        + escape(value) + '</div></div>' for label, value in fields)
    return '<div class="horse-evaluation-grid" style="display:grid;grid-template-columns:minmax(0,1fr) 56px;gap:6px;margin:6px 0;">' + cells + '</div>'
