"""Snapshot boundary: deep-copy saved shadow only, never replay it."""
from copy import deepcopy


def newspaper_v2_snapshot(result):
    keys = (result.race_mode + "_newspaper_v2_shadow", result.race_mode + "_newspaper_v2_class_split_shadow")
    return {key: deepcopy(result.debug_info[key]) for key in keys
            if isinstance((result.debug_info or {}).get(key), dict)}


def restore_newspaper_v2_snapshot(result, snapshot):
    keys = (result.race_mode + "_newspaper_v2_shadow", result.race_mode + "_newspaper_v2_class_split_shadow")
    for key in keys:
        saved = snapshot.get(key)
        if isinstance(saved, dict):
            result.debug_info = {**(result.debug_info or {}), key: deepcopy(saved)}
    return result
