"""Snapshot boundary: deep-copy saved shadow only, never replay it."""
from copy import deepcopy


def newspaper_v2_snapshot(result):
    key = result.race_mode + "_newspaper_v2_shadow"
    payload = (result.debug_info or {}).get(key)
    return {key: deepcopy(payload)} if isinstance(payload, dict) else {}


def restore_newspaper_v2_snapshot(result, snapshot):
    key = result.race_mode + "_newspaper_v2_shadow"
    saved = snapshot.get(key)
    if isinstance(saved, dict):
        result.debug_info = {**(result.debug_info or {}), key: deepcopy(saved)}
    return result
