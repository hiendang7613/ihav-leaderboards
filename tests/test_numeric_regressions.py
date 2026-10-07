from __future__ import annotations

import unittest

from helpers import board, estimate, matches, weights

from ihav_leaderboards.dimensions import choose, conflicts, pareto_charts
from ihav_leaderboards.pareto import frontier
from ihav_leaderboards.scoring import NoScoreError, merge, score_board
from ihav_leaderboards.weights import NoWeightError, allocate, parse_visits_text


class ScoringRegressionTests(unittest.TestCase):
    def aliases(self, slug, names):
        return {(slug, name): name for name in names}

    def test_only_literal_verified_true_contributes(self):
        for marker in (None, 0, 1, "false", "true", False):
            with self.subTest(verified=marker):
                source = board("L", [("A", 10), ("B", 20), ("C", 30), ("D", 100)])
                source["rows"][3]["verified"] = marker
                result = score_board(source, self.aliases("L", "ABCD"))
                self.assertEqual(result["scores"], {"A": 0.0, "B": 50.0, "C": 100.0})
                self.assertEqual(result["unusable"], ["D"])
        source["rows"][3].pop("verified")
        self.assertNotIn("D", score_board(source, self.aliases("L", "ABCD"))["scores"])

    def test_positive_extreme_quality_stays_finite(self):
        result = score_board(board("L", [("A", 0), ("B", 1e306), ("C", 1e307)]),
                             self.aliases("L", "ABC"))
        self.assertEqual(result["status"], "scored")
        self.assertEqual(result["scores"]["A"], 0.0)
        self.assertAlmostEqual(result["scores"]["B"], 10.0)
        self.assertEqual(result["scores"]["C"], 100.0)

    def test_opposite_extreme_quality_preserves_direction(self):
        for direction, expected in (("higher_better", (0.0, 50.0, 100.0)),
                                    ("lower_better", (100.0, 50.0, 0.0))):
            with self.subTest(direction=direction):
                result = score_board(board("L", [("A", -1e308), ("B", 0), ("C", 1e308)],
                                           direction=direction), self.aliases("L", "ABC"))
                self.assertEqual(tuple(result["scores"][key] for key in "ABC"), expected)

    def test_huge_integer_quality_is_unusable_without_crashing(self):
        result = score_board(board("L", [("A", 1), ("B", 2), ("C", 3), ("D", 10 ** 1000)]),
                             self.aliases("L", "ABCD"))
        self.assertEqual(result["scores"], {"A": 0.0, "B": 50.0, "C": 100.0})
        self.assertEqual(result["unusable"], ["D"])

    def test_distinct_conflicting_duplicates_need_one_preferred_row(self):
        source = board("L", [("A", 1), ("A alias", 9), ("B", 2), ("C", 3)])
        aliases = self.aliases("L", "ABC")
        aliases[("L", "A alias")] = "A"
        result = score_board(source, aliases)
        self.assertEqual(result["status"], "unverified")
        self.assertEqual(result["scores"], {})
        self.assertEqual(result["duplicate_conflicts"][0]["candidate"], "A")
        source["rows"][1]["preferred"] = True
        result = score_board(source, aliases)
        self.assertEqual(result["status"], "scored")
        self.assertEqual(result["scores"]["A"], 100.0)
        self.assertEqual(result["scores"]["B"], 0.0)
        self.assertAlmostEqual(result["scores"]["C"], 100.0 / 7.0)
        self.assertEqual(result["duplicates"], ["A"])
        self.assertEqual(result["score_evidence"]["A"]["name"], "A alias")
        self.assertEqual(result["quality_values"]["A"], 9.0)

    def test_multiple_preferred_conflicting_rows_stay_unverified(self):
        source = board("L", [("A", 1), ("A alias", 9), ("B", 2), ("C", 3)])
        source["rows"][0]["preferred"] = source["rows"][1]["preferred"] = True
        aliases = self.aliases("L", "ABC")
        aliases[("L", "A alias")] = "A"
        result = score_board(source, aliases)
        self.assertEqual(result["status"], "unverified")
        self.assertIn("exactly one", result["reason"])

    def test_equal_duplicates_keep_one_verified_value(self):
        source = board("L", [("A", 1), ("A alias", 1), ("B", 2), ("C", 3)])
        aliases = self.aliases("L", "ABC")
        aliases[("L", "A alias")] = "A"
        result = score_board(source, aliases)
        self.assertEqual(result["scores"], {"A": 0.0, "B": 50.0, "C": 100.0})
        self.assertEqual(result["duplicates"], ["A alias"])
        source["rows"][1]["preferred"] = True
        result = score_board(source, aliases)
        self.assertEqual(result["scores"], {"A": 0.0, "B": 50.0, "C": 100.0})
        self.assertEqual(result["duplicates"], ["A"])
        self.assertEqual(result["score_evidence"]["A"]["name"], "A alias")

    def test_equal_duplicates_with_multiple_preferred_rows_stay_unverified(self):
        source = board("L", [("A", 1), ("A alias", 1), ("B", 2), ("C", 3)])
        source["rows"][0]["preferred"] = source["rows"][1]["preferred"] = True
        aliases = self.aliases("L", "ABC")
        aliases[("L", "A alias")] = "A"
        result = score_board(source, aliases)
        self.assertEqual(result["status"], "unverified")
        self.assertEqual(result["scores"], {})
        self.assertEqual(result["duplicate_conflicts"][0]["candidate"], "A")
        self.assertEqual(result["duplicate_conflicts"][0]["preferred_count"], 2)
        self.assertIn("at most one", result["reason"])
        decisions = matches("ABC", ["L"])
        decisions["candidates"][0]["aliases"].append({"board": "L", "name": "A alias"})
        with self.assertRaises(NoScoreError) as caught:
            merge([source], weights({"L": 1}), decisions)
        self.assertEqual(caught.exception.boards[0]["status"], "unverified")

    def test_duplicate_candidate_ids_are_rejected(self):
        decisions = matches("ABC", ["L"])
        decisions["candidates"].append({"id": "A", "name": "different A", "aliases": []})
        with self.assertRaisesRegex(ValueError, "Duplicate candidate id"):
            merge([board("L", [("A", 1), ("B", 2), ("C", 3)])], weights({"L": 1}), decisions)

    def test_conflicting_alias_ownership_is_rejected(self):
        decisions = matches("ABC", ["L"])
        decisions["candidates"][1]["aliases"].append({"board": "L", "name": "A"})
        with self.assertRaisesRegex(ValueError, "Alias.*belongs to both"):
            merge([board("L", [("A", 1), ("B", 2), ("C", 3)])], weights({"L": 1}), decisions)

    def test_duplicate_extracted_and_weight_board_ids_are_rejected(self):
        source = board("L", [("A", 1), ("B", 2), ("C", 3)])
        with self.assertRaisesRegex(ValueError, "Duplicate extracted board slug"):
            merge([source, source], weights({"L": 1}), matches("ABC", ["L"]))
        duplicate_weights = weights({"L": 1})
        duplicate_weights["boards"].append(dict(duplicate_weights["boards"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate weight board slug"):
            merge([source], duplicate_weights, matches("ABC", ["L"]))

    def test_overflowing_mass_total_gives_real_half_weights(self):
        left = board("L", [("A", 1), ("B", 2), ("C", 3)])
        right = board("R", [("A", 3), ("B", 2), ("C", 1)])
        result = merge([left, right], weights({"L": 1e308, "R": 1e308}), matches("ABC", ["L", "R"]))
        self.assertEqual([entry["weight"] for entry in result["boards"]], [0.5, 0.5])
        self.assertEqual(result["counts"]["candidates_ranked"], 3)
        for candidate in result["candidates"]:
            self.assertEqual(candidate["final"], 50.0)
            self.assertEqual(candidate["confidence"], 1.0)

    def test_invalid_selected_mass_has_a_named_input_error(self):
        source = board("L", [("A", 1), ("B", 2), ("C", 3)])
        for mass in (float("inf"), float("nan"), -1, 0, True, 10 ** 1000):
            with self.subTest(mass_type=type(mass).__name__):
                with self.assertRaisesRegex(ValueError, "L.*finite positive"):
                    merge([source], weights({"L": mass}), matches("ABC", ["L"]))

    def test_unrepresentable_positive_weight_is_not_silently_zero(self):
        sources = [board("L", [("A", 1), ("B", 2), ("C", 3)]),
                   board("R", [("A", 3), ("B", 2), ("C", 1)])]
        with self.assertRaisesRegex(ValueError, "L.*representable"):
            merge(sources, weights({"L": 5e-324, "R": 1e308}), matches("ABC", ["L", "R"]))

    def test_tiny_positive_weight_preserves_its_only_candidate_score(self):
        left = board("L", [("A", 1e-10), ("B", 0), ("C", 100)])
        right = board("R", [("B", 0), ("C", 1), ("D", 2)])
        result = merge([left, right], weights({"L": 5e-324, "R": 1}), matches("ABCD", ["L", "R"]))
        a = next(candidate for candidate in result["candidates"] if candidate["id"] == "A")
        self.assertEqual(a["final"], 1e-10)
        self.assertEqual(a["confidence"], 5e-324)
        self.assertIsNotNone(a["rank"])

    def test_unverified_presence_contributes_no_confidence(self):
        left = board("L", [("A", 99), ("B", 1), ("C", 2), ("D", 3)])
        left["rows"][0]["verified"] = 0
        right = board("R", [("A", 3), ("B", 2), ("C", 1)])
        result = merge([left, right], weights({"L": 75, "R": 25}), matches("ABCD", ["L", "R"]))
        a = next(candidate for candidate in result["candidates"] if candidate["id"] == "A")
        self.assertEqual(a["scores"], {"R": 100.0})
        self.assertEqual((a["final"], a["confidence"]), (100.0, 0.25))

    def test_no_score_error_keeps_every_board_reason(self):
        sources = [board("few", [("A", 1), ("B", 2)]),
                   board("flat", [("A", 1), ("B", 1), ("C", 1)]),
                   board("rank", [("A", 1), ("B", 2), ("C", 3)], score_kind="rank_only")]
        with self.assertRaises(NoScoreError) as caught:
            merge(sources, weights({"few": 1, "flat": 1, "rank": 1, "missing": 1}),
                  matches("ABC", ["few", "flat", "rank"]))
        statuses = {item["slug"]: item["status"] for item in caught.exception.boards}
        self.assertEqual(statuses, {"few": "dropped_too_few", "flat": "dropped_flat",
                                   "rank": "rank_only_unscored", "missing": "extract_failed"})
        self.assertTrue(all(item["reason"] and item["weight"] == 0 for item in caught.exception.boards))

    def test_final_retains_visit_match_and_cell_evidence(self):
        source = board("L", [("A", 1), ("B", 2), ("C", 3)], method="direct", snapshot="snapshots/L.json")
        source["rows"][0]["cell"] = "$.rows[0].quality"
        allocations = weights({"L": 1})
        allocations["boards"][0].update(domain="a.example", weight_basis="floor+domain_split(2)",
                                       split=2, visit_period="2026-09", visit_source="fixture")
        decisions = matches("ABC", ["L"])
        decisions["candidates"][0].update(method="exact", evidence="saved identity cell", confidence="low")
        result = merge([source], allocations, decisions)
        saved_board = result["boards"][0]
        self.assertEqual(saved_board["weight_basis"], "floor+domain_split(2)")
        self.assertEqual(saved_board["visit_period"], "2026-09")
        self.assertEqual(saved_board["split"], 2)
        self.assertEqual(saved_board["score_evidence"]["A"]["cell"], "$.rows[0].quality")
        a = next(item for item in result["candidates"] if item["id"] == "A")
        self.assertEqual((a["match_method"], a["match_evidence"], a["match_confidence"]),
                         ("exact", "saved identity cell", "low"))


class WeightRegressionTests(unittest.TestCase):
    def test_huge_integer_visit_is_no_data_and_can_receive_floor(self):
        sources = [{"slug": "huge", "domain": "huge.example", "status": "live"},
                   {"slug": "valid", "domain": "valid.example", "status": "live"}]
        traffic = {"huge.example": estimate("huge.example", 10 ** 1000),
                   "valid.example": estimate("valid.example", 10)}
        result = allocate(sources, traffic)
        by_slug = {entry["slug"]: entry for entry in result["boards"]}
        self.assertEqual(by_slug["huge"]["mass"], 10)
        self.assertEqual(by_slug["huge"]["weight_basis"], "floor+domain_split(1)")
        self.assertIsNone(by_slug["huge"]["monthly_visits"])
        with self.assertRaises(NoWeightError):
            allocate(sources[:1], {"huge.example": traffic["huge.example"]})

    def test_overflowed_visit_label_is_not_returned_as_infinity(self):
        self.assertIsNone(parse_visits_text("9" * 1000 + "B"))

    def test_duplicate_board_ids_cannot_receive_double_traffic(self):
        source = {"slug": "same", "domain": "a.example", "status": "live"}
        with self.assertRaisesRegex(ValueError, "Duplicate board slug"):
            allocate([source, dict(source)], {"a.example": estimate("a.example", 100)})

    def test_selected_mass_cannot_underflow_during_domain_split(self):
        sources = [{"slug": "a", "domain": "a.example", "status": "live"},
                   {"slug": "b", "domain": "a.example", "status": "live"}]
        with self.assertRaisesRegex(ValueError, "a.example.*representable"):
            allocate(sources, {"a.example": estimate("a.example", 5e-324)})

    def test_error_notes_and_source_details_survive_allocation(self):
        sources = [{"slug": "failed", "domain": "failed.example", "status": "live"},
                   {"slug": "valid", "domain": "valid.example", "status": "live"}]
        error = {"error": {"code": "blocked", "notes": ["no retry"]}, "contract_version": 2}
        traffic = {"failed.example": error, "valid.example": estimate("valid.example", 20)}
        result = {item["slug"]: item for item in allocate(sources, traffic)["boards"]}
        self.assertEqual(result["failed"]["visit_error"], error["error"])
        self.assertEqual(result["failed"]["visit_contract_version"], 2)
        self.assertEqual(result["valid"]["visit_source_details"], {"name": "test"})


class DimensionRegressionTests(unittest.TestCase):
    def registry(self, kind):
        return [{"key": "feature", "type": kind, "context": "base", "direction": "none"}]

    def observation(self, oid, value, source="official", **extra):
        observation = {"id": oid, "candidate": "A", "key": "feature", "value": value,
                       "context": "base", "source_type": source}
        observation.update(extra)
        return observation

    def test_missing_bool_and_category_do_not_hide_usable_official_values(self):
        for kind, usable in (("bool", True), ("bool", False), ("category", "EU")):
            with self.subTest(kind=kind, usable=usable):
                observations = [self.observation("missing", None, "leaderboard", board="L"),
                                self.observation("valid", usable)]
                result = choose(self.registry(kind), observations, {"L": 1.0})
                self.assertEqual(result["values"]["A"]["feature"]["value"], usable)
                self.assertEqual(result["values"]["A"]["feature"]["observation"], "valid")
                self.assertEqual(result["conflicts"], [])

    def test_invalid_typed_values_and_unknown_sources_do_not_compete(self):
        for kind, invalid, valid in (("bool", 1, True), ("category", "", "EU"), ("number", 10 ** 1000, 2)):
            with self.subTest(kind=kind):
                observations = [self.observation("invalid", invalid, "leaderboard", board="L"),
                                self.observation("unknown", valid, "model_memory"), self.observation("valid", valid)]
                result = choose(self.registry(kind), observations, {"L": 1.0})
                self.assertEqual(result["values"]["A"]["feature"]["observation"], "valid")
                self.assertEqual(result["unsupported_sources"], 1)

    def test_chosen_value_explains_method_context_and_precedence(self):
        observation = self.observation("valid", 2, method="direct", reason="source cell checked", url="https://example.org")
        chosen = choose(self.registry("number"), [observation], {})["values"]["A"]["feature"]
        self.assertEqual(chosen["method"], "direct")
        self.assertEqual(chosen["context"], "base")
        self.assertEqual(chosen["source_reason"], "source cell checked")
        self.assertIn("official", chosen["reason"])

    def test_conflicts_handles_extreme_opposite_signs(self):
        self.assertTrue(conflicts("number", -1e308, 1e308))
        self.assertFalse(conflicts("number", 1e308, 9e307))
        self.assertFalse(conflicts("number", 10 ** 1000, 1))

    def test_pareto_counts_only_finite_quality_and_dimension_pairs(self):
        registry = [{"key": "price", "type": "number", "direction": "lower_better", "context": "base"}]
        candidates = [{"id": "valid", "final": 80.0}, {"id": "nan", "final": float("nan")},
                      {"id": "huge", "final": 10 ** 1000}, {"id": "no-price", "final": 99.0}]
        values = {key: {"price": {"value": 1}} for key in ("valid", "nan", "huge")}
        result = pareto_charts(registry, values, candidates)["price"]
        self.assertEqual(result["frontier"], ["valid"])
        self.assertEqual((result["plotted"], result["omitted"]), (1, 3))
        self.assertEqual(result["omitted_reasons"], {"unusable_quality": 2, "unusable_dimension": 1})

    def test_frontier_ignores_unrepresentable_integer_axis(self):
        points = [{"id": "invalid", "x": 10 ** 1000, "y": 90}, {"id": "valid", "x": 1, "y": 80}]
        self.assertEqual(frontier(points, "lower_better"), ["valid"])


if __name__ == "__main__":
    unittest.main()
