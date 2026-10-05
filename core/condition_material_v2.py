"""Conditions-only material B. Ranks select comparison groups, never badge votes."""
from copy import deepcopy
import re
import unicodedata


def key_for(mode):
    return mode + '_condition_material_shadow_v2'


def unique_reasons(reasons):
    """Stable dedupe, including existing equivalent joint-condition warnings."""
    out = {}
    seen = set()
    for domain, value in (reasons or {}).items():
        text = unicodedata.normalize('NFKC', str(value)).strip()
        identity = re.sub(r'\s+', '', text)
        if '距離' in text and 'コース' in text and ('下半分' in text or '順位低位' in text):
            identity = 'joint_distance_course_low'
        if identity and identity not in seen:
            out[domain] = str(value).strip()
            seen.add(identity)
    return out


def evaluate_condition_materials(data, mode):
    # Existing hypothesis thresholds are reused verbatim; the base vote is off.
    if mode == 'jra':
        from .jra_material_evidence import evaluate_jra_materials
        out = evaluate_jra_materials(data, include_base=False)
    elif mode == 'nar':
        from .nar_material_evidence import evaluate_nar_materials
        out = evaluate_nar_materials(data, include_base=False)
    else:
        raise ValueError('unsupported race mode')
    for h in out.get('horses', []):
        h['good_reasons'] = unique_reasons(h['good_reasons'])
        h['concern_reasons'] = unique_reasons(h['concern_reasons'])
        h['good'] = '◎' if len(h['good_reasons']) >= 2 else '○' if h['good_reasons'] else '—'
        h['concern'] = '⚠' if len(h['concern_reasons']) >= 2 else '△' if h['concern_reasons'] else '—'
    out['model_version'] = mode + '_condition_material_shadow_v2'
    out['base_evaluation_excluded'] = True
    return out
