"""Opt-in research only. No predictor/UI imports this module.

Freeze predictions before joining outcomes. Never mutate source snapshots.
NAR missing inputs retain their ORIGINAL ordinal slots, matching production.
"""
import copy
import hashlib
import json
import math
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

VERSION = 'rank_corner_research_v2_20261010'
RESEARCH_CUTOFF = '2026-10-10'
NAR_COEFFICIENTS = {'A': (0.01180085, -0.22088414), 'B': (1., 0.),
                    'C': (1., -3.), 'D': (1., -5.)}
FIELDS = ('horse_no', 'name', 'pure', 'pure_rank', 'corner4', 'position',
          'formal_rank', 'formal_mark', 'candidate', 'status', 'formal_score',
          'pace_bonus', 'position_bonus', 'repro_bonus', 'training_bonus',
          'state_bonus', 'pace', 'running_style', 'training', 'interval', 'weight_change')


def number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def positive_int(value):
    n = number(value)
    return int(n) if n is not None and n >= 1 and n.is_integer() else None


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def freeze(race_id, mode, rows, metadata=None):
    """Only allow-listed pre-race facts enter the input hash and ranking.

    Candidate membership must be provided explicitly. Unknown membership/rank
    makes the race unavailable, rather than silently inventing a candidate set.
    Cancellation status must be known at prediction time; late withdrawals are
    handled only by the separate settlement process.
    """
    hs = [{k: copy.deepcopy(r.get(k)) for k in FIELDS} for r in rows]
    for h in hs:
        h['horse_no'] = positive_int(h['horse_no'])
        for k in ('pure_rank', 'formal_rank', 'corner4'):
            h[k] = positive_int(h[k])
        for k in ('pure', 'formal_score', 'pace_bonus', 'position_bonus',
                  'repro_bonus', 'training_bonus', 'state_bonus'):
            h[k] = number(h[k])
    hs.sort(key=lambda h: h['horse_no'] or 99999)
    meta = {k: (metadata or {}).get(k) for k in
            ('date', 'venue', 'distance', 'pace', 'discipline', 'prediction_created_at',
             'scheduled_post_time', 'source_hash', 'formal_origin')}
    inputs = dict(race_id=str(race_id), mode=mode, horses=hs, metadata=meta)
    out = dict(version=VERSION, input_hash=digest(inputs), inputs=inputs,
               research_only=True, models={}, exclusions=[])
    keys = [h['horse_no'] for h in hs]
    if mode not in ('nar', 'jra') or not all(keys) or len(set(keys)) != len(keys):
        out['exclusions'].append('invalid_mode_or_horse_keys')
        return out
    active = [h for h in hs if h['status'] not in ('取消', '除外', 'scratched', 'excluded')]
    if not active or any(h['candidate'] not in (True, False) or ((h['candidate'] or mode == 'jra') and h['pure_rank'] is None) for h in active):
        out['exclusions'].append('missing_candidate_membership_or_ability_rank')
        return out
    pure_order = sorted(active, key=lambda h: (h['pure_rank'] or math.inf, h['horse_no']))
    group = [h for h in pure_order if h['candidate']]
    def model(order, scores, definition, reason='independent_corner_coefficient_comparison'):
        return dict(order=[h['horse_no'] for h in order], candidate_group=[h['horse_no'] for h in group],
                    scores={str(k): v for k, v in scores.items()}, definition=definition,
                    rank_changes=[dict(horse_no=h['horse_no'], pure_rank=h['pure_rank'],
                                       formal_rank=h['formal_rank'], research_rank=i,
                                       delta_from_formal=h['formal_rank']-i if h['formal_rank'] else None,
                                       reason=reason)
                                  for i, h in enumerate(order, 1)])
    if mode == 'nar':
        if not group:
            out['exclusions'].append('empty_protected_group')
            return out
        for label, (ability_coef, corner_coef) in NAR_COEFFICIENTS.items():
            scores = {h['horse_no']: ability_coef*h['pure']+corner_coef*h['corner4']
                      for h in group if h['pure'] is not None and h['corner4'] is not None}
            moving = iter(sorted([h for h in group if h['horse_no'] in scores],
                                key=lambda h: (-scores[h['horse_no']], h['pure_rank'], h['horse_no'])))
            order = pure_order if label == 'B' else [next(moving) if h['horse_no'] in scores else h for h in group] + [h for h in pure_order if not h['candidate']]
            if label == 'B':
                scores = {h['horse_no']: h['pure'] for h in active if h['pure'] is not None}
            out['models'][label] = model(order, scores, dict(ability=ability_coef, corner4=corner_coef,
                missing_policy='original_ability_ordinal_slot_fixed', tie_break='saved_ability_rank_then_horse_no'),
                'saved_ability_rank_then_horse_no' if label == 'B' else 'corner_coefficient_with_missing_slot_protection')
        # Frozen official A is distinguished from replayed A; never label a replay as a historical prediction.
        out['formal_replay_matches'] = all(h['formal_rank'] == i for i, h in enumerate(
            sorted(active, key=lambda h: out['models']['A']['order'].index(h['horse_no'])), 1)) if all(h['formal_rank'] for h in active) else None
        if all(h['formal_rank'] is not None for h in group):
            # Saved A is authoritative even if the current formula replay differs.
            # Keep the mismatch visible; do not replace an historical prediction.
            if len({h['formal_rank'] for h in group}) != len(group):
                out['exclusions'].append('ambiguous_saved_formal_candidate_ranks')
                out['models'].pop('A')
            else:
                official = sorted(group, key=lambda h: (h['formal_rank'], h['horse_no']))
                official += sorted([h for h in active if not h['candidate']],
                                   key=lambda h: (h['formal_rank'] or math.inf, h['pure_rank'] or math.inf, h['horse_no']))
                origin = meta['formal_origin'] or 'saved'
                out['models']['A'] = model(official,
                    {h['horse_no']: h['formal_score'] for h in active if h['formal_score'] is not None},
                    dict(source=origin, ability=NAR_COEFFICIENTS['A'][0], corner4=NAR_COEFFICIENTS['A'][1]),
                    'saved_official_order' if origin == 'saved' else 'explicit_reference_formal_replay')
        else:
            out['models']['A']['definition']['source'] = 'reference_formula_replay_no_saved_formal_order'
    else:
        if meta['discipline'] == 'jump':
            out['exclusions'].append('jump_not_comparable_to_flat')
            return out
        if any(h['formal_rank'] is None or h['formal_score'] is None for h in active):
            out['exclusions'].append('frozen_formal_score_or_rank_missing')
            return out
        out['models']['A'] = model(sorted(active, key=lambda h: (h['formal_rank'], h['horse_no'])),
                                   {h['horse_no']: h['formal_score'] for h in active}, 'frozen_official')
        out['models']['pure_reference'] = model(pure_order, {}, 'ability_reference_not_official_replacement')
        components = ('pace_bonus', 'position_bonus', 'repro_bonus', 'training_bonus', 'state_bonus')
        if any(h['pure'] is None or any(h[k] is None for k in components) or
               abs(h['formal_score'] - h['pure'] - sum(h[k] for k in components)) > .0011 for h in active):
            out['exclusions'].append('saved_score_components_not_reproducible')
            return out
        # Both category-based pace bonus AND exact-position bonus are position-derived.
        # Half strength is a predeclared research hypothesis, never fitted to finishes.
        for label, retain in [('B', 0.), ('C', .5), ('exact_bonus_only_removed', None)]:
            scores = {h['horse_no']: h['formal_score'] - (h['position_bonus'] if retain is None else
                       (1-retain)*(h['pace_bonus']+h['position_bonus'])) for h in active}
            order = sorted(active, key=lambda h: (-scores[h['horse_no']], -h['pure'], h['pure_rank'], h['horse_no']))
            out['models'][label] = model(order, scores, dict(position_derived_retained=retain,
                removed_components=['position_bonus'] if retain is None else ['pace_bonus', 'position_bonus']))
    return out


def comparison_rows(payload):
    """Readable research fields, preserving formal marks and group membership."""
    hs = payload['inputs']['horses']
    best = max((h['pure'] for h in hs if h['pure'] is not None), default=None)
    ranks = {k: {no: i for i, no in enumerate(v['order'], 1)} for k, v in payload['models'].items()}
    records = []
    for h in hs:
        row = dict(race_id=payload['inputs']['race_id'], horse_no=h['horse_no'], name=h['name'],
                   pure_rank=h['pure_rank'], pure=h['pure'], formal_rank=h['formal_rank'],
                   formal_mark=h['formal_mark'], formal_candidate=h['candidate'], corner4=h['corner4'],
                   ability_gap_from_leader=best-h['pure'] if best is not None and h['pure'] is not None else None,
                   input_hash=payload['input_hash'], version=payload['version'])
        for label, lookup in ranks.items():
            row[label+'_rank'] = lookup.get(h['horse_no'])
        row['reason'] = ('予測時点の取消・除外' if h['status'] in ('取消', '除外', 'scratched', 'excluded') else
                         '正式候補外・補助印は維持' if not h['candidate'] else
                         '入力欠損：純能力順の元の枠を保護' if h['pure'] is None or h['corner4'] is None else
                         '保存純能力順位を基準に4角補正だけを比較（正式印は維持）')
        records.append(row)
    return records


def _aware_time(value):
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.utcoffset() is None:
        raise ValueError('Timestamp must contain a timezone')
    return parsed


def write_frozen(path, payload, *, registry_dir=None, phase='historical_research', now=None):
    """One race per shared registry, even if callers use different filenames.

    Future validation requires an unused date after the declared research cutoff
    and an actual write time before the supplied scheduled post time. Use ONE
    shared registry directory across Dashboard/Mobile and all output folders.
    """
    if digest(payload['inputs']) != payload['input_hash']:
        raise ValueError('Input hash mismatch')
    if phase not in ('historical_research', 'future_validation'):
        raise ValueError('Unknown evaluation phase')
    stored = copy.deepcopy(payload)
    if phase == 'future_validation':
        if not payload['models'] or payload['exclusions']:
            raise ValueError('Incomplete research prediction cannot be frozen as future validation')
        meta = payload['inputs']['metadata']
        if date.fromisoformat(str(meta['date'])) <= date.fromisoformat(RESEARCH_CUTOFF):
            raise ValueError('Previously studied date is not future validation')
        current = now or datetime.now(timezone.utc)
        post = _aware_time(meta['scheduled_post_time'])
        created = _aware_time(meta['prediction_created_at'])
        if post.astimezone(timezone(timedelta(hours=9))).date() != date.fromisoformat(str(meta['date'])):
            raise ValueError('Scheduled post date must match the Japanese race date')
        if current.utcoffset() is None or not created <= current < post:
            raise ValueError('Freeze must occur after prediction and before scheduled post time')
        stored['validation'] = dict(phase=phase, frozen_at=current.isoformat(), research_cutoff=RESEARCH_CUTOFF)
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    registry = Path(registry_dir) if registry_dir is not None else path.parent/'.rank_corner_registry'
    registry.mkdir(parents=True, exist_ok=True)
    identity = dict(mode=payload['inputs']['mode'], race_id=payload['inputs']['race_id'])
    claim = registry/(digest(identity)+'.json')
    # O_EXCL claim persists on subsequent write failure: fail closed; never make
    # a failed/ambiguous freeze silently eligible for a second post-result run.
    with claim.open('x', encoding='utf-8') as f:
        json.dump(dict(**identity, output=str(path.resolve()), input_hash=payload['input_hash'],
                       version=payload['version'], phase=phase), f, ensure_ascii=False, sort_keys=True)
    text = json.dumps(stored, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    with path.open('x', encoding='utf-8') as f:
        f.write(text+'\n')
    return stored


def join_outcomes(frozen, outcomes):
    """Separate post-race record. Neither inputs nor frozen ranks are modified."""
    if digest(frozen['inputs']) != frozen['input_hash']:
        raise ValueError('Input hash mismatch')
    if str(outcomes.get('race_id', frozen['inputs']['race_id'])) != frozen['inputs']['race_id']:
        raise ValueError('Outcome race_id mismatch')
    return dict(prediction_hash=digest(frozen), input_hash=frozen['input_hash'],
                outcomes=copy.deepcopy(outcomes), research_prediction=copy.deepcopy(frozen))
