"""NAR newspaper research API, with its own class system and coefficients."""
from .newspaper_v2_engine import evaluate_shadow


def evaluate_nar_newspaper_v2_shadow(rows, race_info, **kwargs):
    return evaluate_shadow(rows, race_info, "nar", **kwargs)
