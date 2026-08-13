from __future__ import annotations

import inspect
import unittest

from core.ver3_ability import VER3_ABILITY_WEIGHTS, calculate_ver3_ability_core


class Ver3AbilityCoreTest(unittest.TestCase):
    def test_formula_uses_only_six_historical_time_indexes(self) -> None:
        self.assertEqual(
            VER3_ABILITY_WEIGHTS,
            {
                "recent_average": 0.15,
                "star_index": 0.30,
                "recent_best": 0.20,
                "latest_index": 0.15,
                "distance_index": 0.10,
                "course_index": 0.10,
            },
        )
        self.assertEqual(sum(VER3_ABILITY_WEIGHTS.values()), 1.0)
        self.assertEqual(
            set(inspect.signature(calculate_ver3_ability_core).parameters),
            {
                "recent_average",
                "star_index",
                "recent_best",
                "latest_index",
                "distance_index",
                "course_index",
            },
        )
        score = calculate_ver3_ability_core(
            recent_average=80,
            star_index=100,
            recent_best=90,
            latest_index=88,
            distance_index=84,
            course_index=82,
        )
        self.assertAlmostEqual(score, 89.8)


if __name__ == "__main__":
    unittest.main()
