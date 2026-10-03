from __future__ import annotations

import unittest

from helpers import estimate, rank_only, visit

from ihav_leaderboards.weights import NoWeightError, allocate, parse_visits_text


def live(slug, domain):
    return {"slug": slug, "domain": domain, "status": "live"}


class WeightTests(unittest.TestCase):
    def test_domain_visits_split_equally_across_its_boards(self):
        boards = [live("hf-a", "huggingface.co"), live("hf-b", "huggingface.co"), live("pwc", "paperswithcode.com")]
        visits = {"huggingface.co": estimate("huggingface.co", 1000), "paperswithcode.com": estimate("paperswithcode.com", 300)}
        out = {e["slug"]: e for e in allocate(boards, visits)["boards"]}
        self.assertEqual(out["hf-a"]["mass"], 500)
        self.assertEqual(out["hf-b"]["mass"], 500)
        self.assertEqual(out["pwc"]["mass"], 300)
        self.assertEqual(out["hf-a"]["weight_basis"], "domain_split(2)")

    def test_rank_only_domain_gets_one_floor_before_split(self):
        boards = [live("a", "big.com"), live("b", "small.com"), live("r1", "ranked.org"), live("r2", "ranked.org")]
        visits = {"big.com": estimate("big.com", 1000), "small.com": estimate("small.com", 40),
                  "ranked.org": rank_only("ranked.org")}
        doc = allocate(boards, visits)
        out = {e["slug"]: e for e in doc["boards"]}
        self.assertEqual(doc["floor"], 40)
        self.assertEqual(out["r1"]["mass"], 20)
        self.assertEqual(out["r2"]["mass"], 20)
        self.assertIsNone(out["r1"]["monthly_visits"])
        self.assertEqual(out["r1"]["weight_basis"], "floor+domain_split(2)")
        self.assertEqual(doc["floor_domains"], ["ranked.org"])

    def test_missing_visit_result_uses_floor(self):
        doc = allocate([live("a", "a.com"), live("b", "b.com")], {"a.com": estimate("a.com", 10)})
        self.assertEqual({e["slug"]: e["mass"] for e in doc["boards"]}, {"a": 10, "b": 10})

    def test_all_rank_only_is_a_diagnostic_not_equal_weights(self):
        boards = [live("a", "a.org"), live("b", "b.org"), live("c", "c.org")]
        visits = {d: rank_only(d) for d in ("a.org", "b.org", "c.org")}
        with self.assertRaises(NoWeightError):
            allocate(boards, visits)

    def test_zero_and_nonfinite_visits_are_not_positive(self):
        boards = [live("a", "a.com"), live("b", "b.com")]
        with self.assertRaises(NoWeightError):
            allocate(boards, {"a.com": estimate("a.com", 0), "b.com": estimate("b.com", float("nan"))})

    def test_only_live_boards_are_weighted(self):
        boards = [live("a", "a.com"), {"slug": "x", "domain": "a.com", "status": "blocked"}]
        doc = allocate(boards, {"a.com": estimate("a.com", 100)})
        self.assertEqual([e["slug"] for e in doc["boards"]], ["a"])
        self.assertEqual(doc["boards"][0]["mass"], 100)

    def test_top_n_selection_by_mass(self):
        boards = [live("b%d" % i, "d%d.com" % i) for i in range(5)]
        visits = {"d%d.com" % i: estimate("d%d.com" % i, (i + 1) * 10) for i in range(5)}
        doc = allocate(boards, visits, top_n=2)
        self.assertEqual([e["slug"] for e in doc["boards"] if e["selected"]], ["b4", "b3"])

    def test_estimate_with_text_label_only(self):
        # Visit counter: kind=estimate may carry monthly_visits=null and a rounded text label.
        text_only = {"domain": "t.com", "kind": "estimate", "monthly_visits": None, "monthly_visits_text": "631.0M"}
        doc = allocate([live("t", "t.com"), live("s", "s.com")], {"t.com": text_only, "s.com": estimate("s.com", 10)})
        out = {e["slug"]: e for e in doc["boards"]}
        self.assertEqual(out["t"]["mass"], 631e6)
        self.assertIsNone(out["t"]["monthly_visits"])
        self.assertEqual(out["t"]["monthly_visits_text"], "631.0M")
        self.assertEqual(out["t"]["weight_basis"], "domain_split(1)")

    def test_estimate_without_number_or_label_uses_floor(self):
        empty = {"domain": "e.com", "kind": "estimate", "monthly_visits": None, "monthly_visits_text": None}
        doc = allocate([live("e", "e.com"), live("s", "s.com")], {"e.com": empty, "s.com": estimate("s.com", 10)})
        self.assertEqual(doc["floor_domains"], ["e.com"])

    def test_error_object_counts_as_no_data(self):
        # Visit counter exit 2/4/5 prints an error object, not a result.
        error = {"domain": "x.com", "error": {"code": "no_data", "notes": ["TrafficLens failed: HTTP 503; no retry was made."]}}
        doc = allocate([live("x", "x.com"), live("s", "s.com")], {"x.com": error, "s.com": estimate("s.com", 10)})
        self.assertEqual(doc["floor_domains"], ["x.com"])

    def test_parse_visits_text(self):
        self.assertEqual(parse_visits_text("631.0M"), 631e6)
        self.assertEqual(parse_visits_text("12k"), 12e3)
        self.assertEqual(parse_visits_text("1,234"), 1234.0)
        self.assertEqual(parse_visits_text("2.5B"), 2.5e9)
        for bad in (None, "", "about 5M", "5T", 7):
            self.assertIsNone(parse_visits_text(bad))

    def test_real_visit_counter_fixtures(self):
        visits = {d: visit(d) for d in ("huggingface.co", "paperswithcode.com", "example-bench.org")}
        boards = [live("hf", "huggingface.co"), live("pwc", "paperswithcode.com"), live("ex", "example-bench.org")]
        out = {e["slug"]: e for e in allocate(boards, visits)["boards"]}
        self.assertEqual(out["hf"]["visit_kind"], "estimate")
        self.assertEqual(out["ex"]["visit_kind"], "rank_only")
        self.assertEqual(out["ex"]["mass"], out["pwc"]["mass"])
        self.assertGreater(out["hf"]["mass"], out["pwc"]["mass"])


if __name__ == "__main__":
    unittest.main()
