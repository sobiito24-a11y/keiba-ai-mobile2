"""Versioned explanation only; no changes to prediction inputs or saved forecasts."""
from copy import deepcopy
import hashlib
import json

KEY = 'race_insight_snapshot'
SCHEMA_VERSION = 1


def display_rows(result):
    """Use the existing display adapters, also when saving without a Streamlit UI."""
    from .prediction_table_ui import horse_key
    from .jockey_positive import overlay
    from .nar_race_diagnostics import build_full_field_comparison
    rows = []
    for table in (result.horse_evaluation, result.overall_table):
        if table is not None and not table.empty:
            rows = table.to_dict('records')
            break
    if result.race_mode == 'nar':
        from .nar_top5_order import overlay_saved, sort_key
        rows = overlay_saved(result, rows)
    rows = overlay(result, rows)
    comparison = None
    if result.race_mode == 'jra':
        from .jra_formal_snapshot import saved_formal_comparison
        comparison = saved_formal_comparison(result)
    if not rows:
        return list((comparison or {}).get('rows', []))
    if comparison is None:
        comparison = build_full_field_comparison(rows, race_mode=result.race_mode,
                                                sort_mode='current', race_info=result.race_info or {})
    by = {horse_key(h): h for h in comparison.get('rows', [])}
    rows = [dict(h, **by.get(horse_key(h), {})) for h in rows]
    if result.race_mode == 'nar':
        from .position_signals import nar_position_reference
        for h in rows:
            h.update(nar_position_reference(h))
        return sorted(rows, key=sort_key)
    from .jra_rank_display import official_jra_result_rows
    def order(h):
        from .prediction_table_ui import number
        rank = number(h.get('_display_jra_top5_rank', h.get('jra_top5_rank')))
        score = number(h.get('jra_top5_score'))
        ability = number(h.get('jra_pure_ability_score'))
        return (rank if rank is not None else 999,
                -(score if score is not None else -9999),
                -(ability if ability is not None else -9999), int(horse_key(h) or 999))
    return official_jra_result_rows(result, sorted(rows, key=order))


def saved(result):
    value = (result.debug_info or {}).get(KEY)
    if isinstance(value, dict) and isinstance(value.get('insight'), dict):
        sections = value['insight'].get('sections')
        if isinstance(sections, list) and len(sections) == 5:
            return deepcopy(value)
    return None


def resolve(result, rows=None, development=None):
    value = saved(result)
    if value is not None:
        return value['insight'], 'saved'
    from .race_development import snapshot, compose_commentary
    from .race_insight import generate
    if rows is None:
        rows = display_rows(result)
    if development is None:
        development = compose_commentary(snapshot(result), rows, result.race_mode)
    restored = any(getattr(result, key, False) for key in
                   ('_race_insight_restored', '_material_snapshot_restored', '_jra_snapshot_restored'))
    return generate(result, rows, development), 'reference' if restored else 'current'


def freeze(result):
    """Return a copy for a NEW export; never rewrite old files or mutate result."""
    value = saved(result)
    if value is not None:
        return value
    from .race_development import snapshot, compose_commentary
    rows = display_rows(result)
    development = compose_commentary(snapshot(result), rows, result.race_mode)
    insight, origin = resolve(result, rows, development)
    identity = dict(race_mode=result.race_mode,
                    race_id=(result.race_info or {}).get('race_id'),
                    prediction_created_at=result.created_at,
                    source_files={str(k): str(v) for k, v in (result.source_files or {}).items()})
    # Only evidence actually read by explanation. No results, odds or payouts.
    inputs = dict(identity=identity, horses=insight['horses'],
                  pace_prediction=development['pace_prediction'])
    canonical = json.dumps(inputs, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    # Deterministic serialization; export time belongs to the containing snapshot.
    # Do not invent a commentary-generation time from the prediction timestamp.
    return dict(schema_version=SCHEMA_VERSION, generation_version=insight['version'],
                generation_origin=origin,
                input_identity=identity, input_sha256=hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
                input_hash_scope='identity_and_explanation_facts_v1', inputs=inputs,
                insight=deepcopy(insight))


def restore(result, payload):
    """Prefer a saved explanation, regardless of the current generator version."""
    result._race_insight_restored = True
    if saved(result) is not None:
        return
    value = payload.get(KEY) or (payload.get('mobile_snapshot') or {}).get(KEY)
    if isinstance(value, dict) and isinstance(value.get('insight'), dict):
        result.debug_info = {**(result.debug_info or {}), KEY: deepcopy(value)}
