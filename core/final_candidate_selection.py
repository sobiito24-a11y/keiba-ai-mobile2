"""Read-only final-candidate membership and ordering over the active UI model.

This projection never elects new reference horses.  The predictor's formal
membership and already-selected check marks are the only membership inputs.
"""
from math import inf

from .prediction_table_ui import number, text
from .game_ui_candidate_evidence import normalized_mark


def formal_score(horse):
    """Return a recorded active-model score, never a display-only reference.

    Model B scores take precedence over the copied model A metadata.  An
    explicit ``candidate_formal_score`` of None means that the formal score is
    unavailable; it must not fall through to a reference equation or zero.
    """
    if horse.get('active_model') == 'B':
        return number((horse.get('model_b') or {}).get('score'))
    if 'candidate_formal_score' in horse:
        return number(horse['candidate_formal_score'])
    if horse.get('mode') == 'nar':
        reference = horse.get('reference_score')
        if isinstance(reference, dict):
            return number(reference.get('value')) if reference.get('kind') == 'official' else None
        if '_decision_score' in horse:
            return number(horse['_decision_score'])
        # Legacy projections without provenance can only attest to Top5 scores.
        return number(horse.get('internal_score')) if horse.get('formal_member') is True else None
    raw = number(horse.get('internal_score'))
    return raw if raw is not None else number(horse.get('score'))


def _number_order(horse):
    value = number(horse.get('no'))
    return value if value is not None and value > 0 else inf


def _rank(horse):
    value = number(horse.get('rank'))
    return value if value is not None and value > 0 else inf


def _identity(horse, index):
    no = number(horse.get('no'))
    if no is not None and no > 0 and no.is_integer():
        return ('no', int(no))
    # Missing horse numbers remain renderable without merging unrelated rows.
    name = text(horse.get('name'))
    return ('name', name) if name and name not in ('—', '-', '未取得') else ('row', index)


def _reference_order(horse, index):
    if horse.get('mode') == 'nar':
        saved = horse.get('reference_selection') or {}
        source = saved.get('source', horse.get('nar_check_source'))
        pure = number(saved.get('pure_rank', horse.get('nar_check_pure_rank')))
        if pure is None:
            pure = number(horse.get('ability_rank'))
        corner = number(saved.get('corner4_rank', horse.get('nar_check_corner4_rank')))
        if corner is None:
            corner = number(horse.get('corner'))
        jockey = number(saved.get('jockey_place_rate', horse.get('nar_check_jockey_place_rate')))
        if jockey is None:
            audit = (horse.get('candidate_evidence') or {}).get('audit') or {}
            jockey = number((audit.get('jockey') or {}).get('current_jockey_place_rate'))
        # Frozen references use resolve_saved()'s own tie-break (pure rank,
        # horse number).  Do not introduce today's corner/jockey preference
        # when choosing between two already-saved decisions.
        frozen = source in ('saved_nar_check_selected', 'saved_overall_display_mark')
        if frozen:
            return (False, pure if pure is not None else inf,
                    _number_order(horse), 0, index)
        # New select() decisions retain pure rank, corner, jockey rate and the
        # original row order.  Both paths still consume existing ✓ only.
        return (not frozen, pure if pure is not None else inf,
                corner if corner is not None else inf,
                -jockey if jockey is not None else inf, index)
    # JRA's existing final_mark_sort_key, restricted to the already-existing ✓.
    score = formal_score(horse)
    return (_rank(horse), -score if score is not None else inf,
            _number_order(horse), index)


def select_indices(view, order='no'):
    """Return at most five formal horses plus one existing reference, no copies.

    The returned indices refer to the original view, which is never mutated.
    Deduplication favours the formal entry even if a duplicate reference occurs
    earlier.  Sorting only reorders these indices and never changes membership.
    """
    if order not in ('no', 'score'):
        raise ValueError('表示順は no または score を指定してください')
    formal = sorted((i for i, h in enumerate(view) if h.get('formal_member') is True),
                    key=lambda i: (_rank(view[i]), _number_order(view[i]), i))
    chosen, identities = [], set()
    for i in formal:
        identity = _identity(view[i], i)
        if identity in identities:
            continue
        chosen.append(i)
        identities.add(identity)
        if len(chosen) == 5:
            break
    references = sorted((i for i, h in enumerate(view)
                         if h.get('formal_member') is not True
                         and normalized_mark(h.get('mark')) == '✓'),
                        key=lambda i: _reference_order(view[i], i))
    for i in references:
        identity = _identity(view[i], i)
        if identity not in identities:
            chosen.append(i)
            break
    if order == 'score':
        def key(i):
            value = formal_score(view[i])
            return (value is None, -value if value is not None else 0,
                    _number_order(view[i]), i)
    else:
        def key(i):
            return (_number_order(view[i]), i)
    return sorted(chosen, key=key)


def candidates(view, label):
    """The existing metric-group contract, limited to the final UI surface."""
    rows = select_indices(view)
    return dict(key='final', label=label, kind='candidates', rows=rows, cards=[],
                eligible=len(rows), total=len(view),
                note='正式Top5と既存の参考候補から最大6頭。馬番順では正式印・順位・最終評価スコアを表示しません。')
