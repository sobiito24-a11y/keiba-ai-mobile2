"""JRA newspaper research API; legacy v2_logic is unrelated."""
from .newspaper_v2_engine import evaluate_shadow


def evaluate_jra_newspaper_v2_shadow(rows, race_info, **kwargs):
    return evaluate_shadow(rows, race_info, "jra", **kwargs)
