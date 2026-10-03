from __future__ import annotations

import unittest

from helpers import board, matches, weights

from ihav_leaderboards.scoring import NoScoreError, merge, score_board


def by_id(final):
    return {c["id"]: c for c in final["candidates"]}


class ScoreBoardTests(unittest.TestCase):
    def aliases(self, slug, names):
        return {(slug, n): n for n in names}

    def test_min_max_to_0_100(self):
        out = score_board(board("L", [("A", 10), ("B", 20), ("C", 30)]), self.aliases("L", "ABC"))
        self.assertEqual(out["status"], "scored")
        self.assertEqual(out["scores"], {"A": 0.0, "B": 50.0, "C": 100.0})

    def test_lower_better_is_inverted(self):
        out = score_board(board("L", [("A", 1.0), ("B", 2.0), ("C", 5.0)], direction="lower_better"),
                          self.aliases("L", "ABC"))
        self.assertEqual(out["scores"]["A"], 100.0)
        self.assertEqual(out["scores"]["C"], 0.0)
        self.assertEqual(out["scores"]["B"], 75.0)

    def test_fewer_than_three_scores_is_dropped(self):
        out = score_board(board("L", [("A", 1), ("B", 2)]), self.aliases("L", "AB"))
        self.assertEqual(out["status"], "dropped_too_few")

    def test_flat_board_is_dropped(self):
        out = score_board(board("L", [("A", 7), ("B", 7), ("C", 7)]), self.aliases("L", "ABC"))
        self.assertEqual(out["status"], "dropped_flat")

    def test_three_rows_but_one_not_finite_is_too_few(self):
        rows = [("A", 1), ("B", 2), ("C", float("inf"))]
        self.assertEqual(score_board(board("L", rows), self.aliases("L", "ABC"))["status"], "dropped_too_few")

    def test_duplicate_rows_count_once(self):
        b = board("L", [("A", 1), ("A v2", 9), ("B", 2), ("C", 3)])
        aliases = {("L", "A"): "A", ("L", "A v2"): "A", ("L", "B"): "B", ("L", "C"): "C"}
        out = score_board(b, aliases)
        self.assertEqual(out["duplicates"], ["A v2"])
        self.assertEqual(out["scores"]["A"], 0.0)

    def test_unverified_row_is_not_scored(self):
        b = board("L", [("A", 1), ("B", 2), ("C", 3), ("D", 4)])
        b["rows"][3]["verified"] = False
        out = score_board(b, self.aliases("L", "ABCD"))
        self.assertNotIn("D", out["scores"])
        self.assertEqual(out["unusable"], ["D"])

    def test_rank_only_board_is_not_mixed_into_metric_score(self):
        out = score_board(board("L", [("A", 1), ("B", 2), ("C", 3)], score_kind="rank_only"), self.aliases("L", "ABC"))
        self.assertEqual(out["status"], "rank_only_unscored")
        self.assertEqual(out["scores"], {})

    def test_preset_unverified_board_stays_unverified(self):
        out = score_board(board("L", [("A", 1), ("B", 2), ("C", 3)], status="unverified"), self.aliases("L", "ABC"))
        self.assertEqual(out["status"], "unverified")


class MergeTests(unittest.TestCase):
    def test_missing_value_gives_no_score_and_no_confidence(self):
        # Review F2: A=10, B=20, C=30, D=N/A on L1; D only scores on L2.
        l1 = board("L1", [("A", 10), ("B", 20), ("C", 30), ("D", "N/A")])
        l2 = board("L2", [("A", 1), ("B", 2), ("D", 3)])
        final = merge([l1, l2], weights({"L1": 75, "L2": 25}), matches("ABCD", ["L1", "L2"]))
        c = by_id(final)
        self.assertNotIn("L1", c["D"]["scores"])
        self.assertAlmostEqual(c["D"]["confidence"], 0.25)
        self.assertAlmostEqual(c["D"]["final"], 100.0)
        self.assertAlmostEqual(c["C"]["confidence"], 0.75)
        self.assertAlmostEqual(c["C"]["final"], 100.0)
        # A: 0 on L1 and 0 on L2.
        self.assertAlmostEqual(c["A"]["final"], 0.0)
        # B: 50 on both boards.
        self.assertAlmostEqual(c["B"]["final"], 50.0)
        self.assertAlmostEqual(c["B"]["confidence"], 1.0)

    def test_weights_renormalize_over_scored_boards_only(self):
        good = board("G", [("A", 1), ("B", 2), ("C", 3)])
        dropped = board("X", [("A", 1), ("B", 2)])
        final = merge([good, dropped], weights({"G": 10, "X": 90}), matches("ABC", ["G", "X"]))
        status = {b["slug"]: b for b in final["boards"]}
        self.assertEqual(status["X"]["status"], "dropped_too_few")
        self.assertEqual(status["X"]["weight"], 0.0)
        self.assertAlmostEqual(status["G"]["weight"], 1.0)
        self.assertAlmostEqual(by_id(final)["A"]["confidence"], 1.0)

    def test_candidate_without_eligible_score_has_null_final_and_no_rank(self):
        final = merge([board("G", [("A", 1), ("B", 2), ("C", 3)])], weights({"G": 1}), matches("ABCZ", ["G"]))
        z = by_id(final)["Z"]
        self.assertIsNone(z["final"])
        self.assertIsNone(z["rank"])
        self.assertEqual(final["candidates"][-1]["id"], "Z")

    def test_no_scored_board_raises(self):
        with self.assertRaises(NoScoreError):
            merge([board("X", [("A", 1), ("B", 2)])], weights({"X": 5}), matches("AB", ["X"]))

    def test_unextracted_selected_board_is_reported(self):
        final = merge([board("G", [("A", 1), ("B", 2), ("C", 3)])], weights({"G": 1, "missing": 9}),
                      matches("ABC", ["G"]))
        status = {b["slug"]: b["status"] for b in final["boards"]}
        self.assertEqual(status["missing"], "extract_failed")
        self.assertEqual(final["counts"], {"selected": 2, "scored": 1, "candidates_ranked": 3, "candidates_unranked": 0})

    def test_unselected_boards_are_ignored(self):
        w = {"boards": [{"slug": "G", "mass": 1, "selected": True}, {"slug": "H", "mass": 99, "selected": False}]}
        final = merge([board("G", [("A", 1), ("B", 2), ("C", 3)]), board("H", [("A", 3), ("B", 2), ("C", 1)])],
                      w, matches("ABC", ["G", "H"]))
        self.assertEqual(by_id(final)["C"]["final"], 100.0)

    def test_ranking_ties_break_by_confidence_then_name(self):
        l1 = board("L1", [("A", 3), ("B", 3), ("C", 1)])
        l2 = board("L2", [("B", 3), ("C", 2), ("D", 1)])
        final = merge([l1, l2], weights({"L1": 1, "L2": 1}), matches("ABCD", ["L1", "L2"]))
        order = [c["id"] for c in final["candidates"]]
        # A=100 (conf 0.5), B=100 (conf 1.0) -> B first.
        self.assertEqual(order[:2], ["B", "A"])

    def test_final_stays_within_0_100(self):
        l1 = board("L1", [("A", -5), ("B", 0), ("C", 1e9)])
        l2 = board("L2", [("A", 0.1), ("B", 0.2), ("C", 0.3)], direction="lower_better")
        final = merge([l1, l2], weights({"L1": 3, "L2": 1}), matches("ABC", ["L1", "L2"]))
        for c in final["candidates"]:
            self.assertGreaterEqual(c["final"], 0.0)
            self.assertLessEqual(c["final"], 100.0)


if __name__ == "__main__":
    unittest.main()
