from __future__ import annotations

import unittest

import helpers  # noqa: F401  (adds the core to sys.path)

from ihav_leaderboards.dimensions import choose, conflicts, pareto_charts
from ihav_leaderboards.pareto import frontier


class ParetoTests(unittest.TestCase):
    def test_lower_better_frontier(self):
        points = [{"id": "cheap", "x": 1, "y": 50}, {"id": "best", "x": 10, "y": 90},
                  {"id": "bad", "x": 10, "y": 40}, {"id": "mid", "x": 5, "y": 70}]
        self.assertEqual(frontier(points, "lower_better"), ["cheap", "best", "mid"])

    def test_higher_better_frontier(self):
        points = [{"id": "fast", "x": 100, "y": 60}, {"id": "slow", "x": 10, "y": 60}]
        self.assertEqual(frontier(points, "higher_better"), ["fast"])

    def test_equal_points_are_both_kept(self):
        points = [{"id": "a", "x": 1, "y": 1}, {"id": "b", "x": 1, "y": 1}]
        self.assertEqual(frontier(points, "lower_better"), ["a", "b"])

    def test_null_and_nonfinite_are_excluded(self):
        points = [{"id": "a", "x": None, "y": 99}, {"id": "b", "x": float("nan"), "y": 99}, {"id": "c", "x": 5, "y": 1}]
        self.assertEqual(frontier(points, "lower_better"), ["c"])

    def test_bad_direction_raises(self):
        with self.assertRaises(ValueError):
            frontier([], "none")


REGISTRY = [{"key": "price", "unit": "USD/1k pages", "type": "number", "direction": "lower_better", "context": "base-ocr"}]


class DimensionTests(unittest.TestCase):
    def test_context_filter_runs_before_precedence(self):
        observations = [
            {"id": "lb", "candidate": "A", "key": "price", "value": 50, "context": "layout-ocr",
             "source_type": "leaderboard", "board": "heavy"},
            {"id": "doc", "candidate": "A", "key": "price", "value": 1.5, "context": "base-ocr",
             "source_type": "official"},
        ]
        out = choose(REGISTRY, observations, {"heavy": 0.9})
        self.assertEqual(out["values"]["A"]["price"]["observation"], "doc")
        self.assertEqual(out["out_of_context"], 1)

    def test_leaderboard_beats_official_and_heavier_board_wins(self):
        observations = [
            {"id": "doc", "candidate": "A", "key": "price", "value": 1.0, "context": "base-ocr", "source_type": "official"},
            {"id": "light", "candidate": "A", "key": "price", "value": 2.0, "context": "base-ocr",
             "source_type": "leaderboard", "board": "L2"},
            {"id": "heavy", "candidate": "A", "key": "price", "value": 2.1, "context": "base-ocr",
             "source_type": "leaderboard", "board": "L1"},
        ]
        out = choose(REGISTRY, observations, {"L1": 0.7, "L2": 0.3})
        self.assertEqual(out["values"]["A"]["price"]["observation"], "heavy")
        self.assertEqual([c["other"] for c in out["conflicts"]], ["doc"])

    def test_newer_date_wins_within_same_source_rank(self):
        observations = [
            {"id": "old", "candidate": "A", "key": "price", "value": 2, "context": "base-ocr",
             "source_type": "official", "date": "2026-01-01"},
            {"id": "new", "candidate": "A", "key": "price", "value": 2, "context": "base-ocr",
             "source_type": "official", "date": "2026-09-01"},
        ]
        self.assertEqual(choose(REGISTRY, observations, {})["values"]["A"]["price"]["observation"], "new")

    def test_typed_conflicts(self):
        self.assertTrue(conflicts("bool", True, False))
        self.assertFalse(conflicts("category", "eu", "eu"))
        self.assertFalse(conflicts("number", 0, 0))
        self.assertFalse(conflicts("number", 10, 11))
        self.assertTrue(conflicts("number", 10, 13))

    def test_pareto_chart_omits_candidates_without_value(self):
        candidates = [{"id": "A", "final": 90.0}, {"id": "B", "final": 50.0}, {"id": "C", "final": None}]
        values = {"A": {"price": {"value": 10}}, "B": {"price": {"value": 1}}}
        chart = pareto_charts(REGISTRY, values, candidates)["price"]
        self.assertEqual(chart["frontier"], ["A", "B"])
        self.assertEqual((chart["plotted"], chart["omitted"]), (2, 1))


if __name__ == "__main__":
    unittest.main()
