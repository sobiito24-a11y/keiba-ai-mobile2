"""Capture the existing formal producer once on fresh generation.

Do not merge reproduction inputs here: that change is research-only until
approved. Consumers return copies of the frozen comparison, never V2 output.
"""
from copy import deepcopy

KEY = 'jra_formal_comparison_snapshot'


def saved_formal_comparison(result):
    saved = (getattr(result, 'debug_info', {}) or {}).get(KEY)
    return deepcopy(saved) if result.race_mode == 'jra' and isinstance(saved, dict) else None


def freeze_fresh_formal(result):
    if result.race_mode != 'jra' or saved_formal_comparison(result) is not None:
        return result
    from .nar_race_diagnostics import build_full_field_comparison
    from .jra_win_probability import jra_win_probability_snapshot
    source = []
    for table in (result.horse_evaluation, result.overall_table):
        if table is not None and not table.empty:
            source = table.to_dict('records')
            break
    saved = build_full_field_comparison(source, race_mode='jra', sort_mode='current', race_info=result.race_info or {})
    result.debug_info = {**(result.debug_info or {}), KEY: deepcopy(saved)}
    result.debug_info['jra_win_probability_calibration'] = jra_win_probability_snapshot(result)
    return result


def formal_snapshot_fields(result):
    saved = saved_formal_comparison(result)
    return {KEY: saved} if saved is not None else {}
