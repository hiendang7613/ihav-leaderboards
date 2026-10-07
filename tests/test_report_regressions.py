from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from helpers import ROOT
from test_render import minimal_final

from ihav_leaderboards.render import to_html
from ihav_leaderboards.tables import to_csv, to_markdown


def walk(node):
    yield node
    for child in node["children"]:
        yield from walk(child)


def dimension(key, kind="number", direction="lower_better"):
    return {"key": key, "label": key.title(), "type": kind, "direction": direction,
            "unit": "test units", "context": "same workload"}


def chosen(value, **extra):
    item = {"value": value, "context": "same workload", "observation": "obs-1",
            "source_type": "official", "url": "https://example.com/source", "date": "2026-10-01",
            "method": "saved snapshot", "reason": "Newest comparable official observation"}
    item.update(extra)
    return item


class ExportRegressionTests(unittest.TestCase):
    def test_csv_records_literal_synthetic_flag_on_every_row(self):
        for flag, expected in ((True, "true"), (False, "false"), (None, "false"), ("true", "false"), (1, "false")):
            with self.subTest(flag=flag):
                final = minimal_final(synthetic=flag, registry=[dimension("numeric")],
                                      dimensions={"a": {"numeric": chosen(-2.5)}})
                final["candidates"].append({"id": "none", "name": "No score", "rank": None,
                                            "final": None, "confidence": None, "scores": {}})
                rows = list(csv.reader(io.StringIO(to_csv(final))))
                self.assertEqual(rows[0], ["rank", "candidate", "final_score", "confidence", "numeric", "synthetic"])
                self.assertEqual([row[-1] for row in rows[1:]], [expected, expected])
                self.assertEqual(rows[1][4], "-2.5")

    def test_markdown_keeps_dependency_notices_and_final_url(self):
        notices = ["Dependency package versions were not recorded by the host.",
                   "Legacy saved visit contracts retained without migration: old.example."]
        final = minimal_final(warnings=notices,
                              collection=[{"slug": "b", "final_url": "https://example.com/final", "status": "live"}])
        page = to_markdown(final)
        for notice in notices:
            self.assertIn(notice, page)
        self.assertIn("https://example.com/final", page)

    def test_csv_neutralizes_formula_text_but_keeps_negative_numbers(self):
        for text in ("=1+1", "+SUM(1,2)", "-cmd", "@SUM(1,2)", " \t\r\n=1+1", "\x00\ufeff+cmd"):
            with self.subTest(text=text):
                final = minimal_final(registry=[dimension(text, "category"), dimension("numeric")])
                final["candidates"][0]["name"] = text
                final["dimensions"] = {"a": {text: chosen(text), "numeric": chosen(-2.5)}}
                rows = list(csv.reader(io.StringIO(to_csv(final))))
                self.assertEqual(rows[0][4], "'" + text)
                self.assertEqual(rows[1][1], "'" + text)
                self.assertEqual(rows[1][4], "'" + text)
                self.assertEqual(rows[1][5], "-2.5")

    def test_markdown_escapes_every_dynamic_table_cell(self):
        final = minimal_final(registry=[dimension("key|\r\nheader", "category")])
        final["candidates"][0]["name"] = "A|\r\nB"
        final["dimensions"] = {"a": {"key|\r\nheader": chosen("value|\r\nnext")}}
        final["boards"][0].update(status="bad|\r\nstatus", reason="reason|\r\nnext")
        page = to_markdown(final)
        self.assertIn("key\\| header", page)
        self.assertIn("value\\| next", page)
        self.assertIn("bad\\| status", page)
        self.assertIn("reason\\| next", page)
        self.assertNotIn("\r", page)

    def test_markdown_displays_synthetic_and_source_provenance(self):
        final = minimal_final(synthetic=True, registry=[dimension("price")],
                              dimensions={"a": {"price": chosen(3)}},
                              publication={"source_sha256": {"sources/page.html": "a" * 64}})
        final["boards"][0].update(weight_basis="policy_floor", domain="example.com", split=2,
                                  visit_period={"start": "2026-09-01", "end": "2026-09-30"},
                                  visit_source="counter", visit_kind="no_data")
        page = to_markdown(final)
        for expected in ("Synthetic", "policy_floor", "example.com", "2026-09-30", "counter",
                         "saved snapshot", "Newest comparable official observation", "sources/page.html", "a" * 64):
            self.assertIn(expected, page)


@unittest.skipUnless(shutil.which("node"), "Node.js is unavailable; DOM checks are offline only")
class ReportDomRegressionTests(unittest.TestCase):
    def dom(self, final):
        result = subprocess.run([shutil.which("node"), str(ROOT / "tests/report_dom_harness.js")],
                                input=to_html(final), text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_frontier_membership_is_safe_for_prototype_names(self):
        candidates = [{"id": name, "name": name, "final": 50.0, "confidence": 1.0,
                       "rank": i + 1, "scores": {"b": 50.0}}
                      for i, name in enumerate(("constructor", "__proto__", "toString", "best"))]
        candidates[-1]["final"] = 100.0
        final = minimal_final(candidates=candidates, registry=[dimension("price")],
                              dimensions={c["id"]: {"price": chosen(1 if c["id"] == "best" else 2)} for c in candidates},
                              pareto={"price": {"direction": "lower_better", "frontier": ["best"], "plotted": 4, "omitted": 0}})
        dom = self.dom(final)
        marks = [n for n in walk(dom["pareto"]) if n["name"] == "circle" and n["attrs"].get("class") == "mark"]
        self.assertEqual(sum(m["attrs"]["fill"] == "var(--series-1)" for m in marks), 1)
        self.assertEqual(sum(m["attrs"]["fill"] == "var(--other)" for m in marks), 3)

    def test_price_is_the_initial_headline_dimension(self):
        final = minimal_final(registry=[dimension("latency"), dimension("price")],
                              dimensions={"a": {"latency": chosen(2), "price": chosen(1)}},
                              pareto={key: {"direction": "lower_better", "frontier": ["a"], "plotted": 1, "omitted": 0}
                                      for key in ("latency", "price")})
        dom = self.dom(final)
        self.assertEqual(dom["dim"]["value"], "price")
        self.assertEqual(dom["pareto-name"]["text"], "Price")

    def test_dimension_bars_include_direction_none_and_unranked_candidates(self):
        final = minimal_final(registry=[dimension("languages", direction="none")],
                              dimensions={"a": {"languages": chosen(5)}, "dimension-only": {"languages": chosen(10)}})
        final["candidates"].append({"id": "dimension-only", "name": "Dimension only", "final": None,
                                    "confidence": None, "rank": None, "scores": {}})
        dom = self.dom(final)
        card = dom["dimensions"]["text"]
        self.assertIn("Languages", card)
        self.assertIn("Dimension only", card)
        self.assertIn("2 plotted", card)
        self.assertIn("no preferred direction", card)

    def test_badges_and_chosen_source_and_conflicts_are_visible(self):
        final = minimal_final(registry=[dimension("support", "bool", "none"), dimension("tier", "category", "none")],
                              dimensions={"a": {"support": chosen(True), "tier": chosen("free")}},
                              dimension_conflicts=[{"candidate": "a", "key": "tier", "chosen": "obs-1", "other": "obs-2"}])
        dom = self.dom(final)
        badges = [n["text"] for n in walk(dom["table"]) if n["className"] == "badge"]
        self.assertEqual(badges, ["yes", "free"])
        self.assertIn("saved snapshot", dom["evidence"]["text"])
        self.assertIn("Newest comparable official observation", dom["evidence"]["text"])
        self.assertIn("obs-2", dom["evidence"]["text"])

    def test_chart_omissions_and_weight_basis_are_visible(self):
        final = minimal_final()
        final["candidates"] = [{"id": str(i), "name": "Candidate %d" % i, "rank": i + 1,
                                "final": 100.0 - i, "confidence": 1.0, "scores": {"b": 100.0 - i}} for i in range(27)]
        final["candidates"].append({"id": "none", "name": "No score", "rank": None,
                                    "final": None, "confidence": None, "scores": {}})
        final["boards"][0].update(weight_basis="policy_floor", domain="example.com", split=2,
                                  visit_period="2026-09", visit_source="counter")
        final["boards"].append({"slug": "rank-only", "status": "rank_only_unscored", "reason": "no metric", "weight": 0})
        dom = self.dom(final)
        for element in ("rank-note", "grid-note"):
            self.assertIn("2", dom[element]["text"])
            self.assertIn("display limit", dom[element]["text"])
            self.assertIn("1", dom[element]["text"])
            self.assertIn("no usable quality score", dom[element]["text"])
        self.assertIn("rank_only_unscored", dom["grid-note"]["text"])
        for expected in ("policy_floor", "example.com", "2026-09", "counter"):
            self.assertIn(expected, dom["weights"]["text"])
        self.assertIn("0 leaderboards omitted", dom["weights-note"]["text"])

    def test_synthetic_banner_and_source_hashes_use_inert_text(self):
        final = minimal_final(synthetic=True,
                              publication={"generation": "generation-1", "source_sha256": {"sources/<page>.html": "a" * 64}})
        dom = self.dom(final)
        self.assertIn("Synthetic", dom["synthetic"]["text"])
        self.assertNotEqual(dom["synthetic"]["style"].get("display"), "none")
        self.assertIn("sources/<page>.html", dom["evidence"]["text"])
        self.assertIn("a" * 64, dom["evidence"]["text"])

    def test_extreme_finite_dimension_values_keep_svg_coordinates_finite(self):
        candidates = [{"id": name, "name": name, "final": float(i * 50), "confidence": 1.0,
                       "rank": i + 1, "scores": {"b": float(i * 50)}} for i, name in enumerate(("low", "mid", "high"))]
        final = minimal_final(candidates=candidates, registry=[dimension("extreme")],
                              dimensions={name: {"extreme": chosen(value)} for name, value in zip(("low", "mid", "high"), (-1e308, 0, 1e308))},
                              pareto={"extreme": {"direction": "lower_better", "frontier": ["low", "mid", "high"], "plotted": 3, "omitted": 0}})
        dom = self.dom(final)
        for element in ("pareto", "dimensions"):
            for node in walk(dom[element]):
                for key, value in node["attrs"].items():
                    if key in ("cx", "cy", "x", "y", "width", "height", "d", "points", "viewBox"):
                        self.assertNotIn("Infinity", value)
                        self.assertNotIn("NaN", value)

    def test_match_provenance_uses_saved_match_fields(self):
        final = minimal_final()
        final["candidates"][0].update(match_method="source-supported alias", match_confidence=0.6,
                                      match_evidence="Same vendor, version and workload", aliases=[{"board": "b", "name": "alias"}])
        dom = self.dom(final)
        for expected in ("source-supported alias", "0.6", "Same vendor, version and workload", "alias"):
            self.assertIn(expected, dom["evidence"]["text"])
            self.assertIn(expected, to_markdown(final))

    def test_collection_and_selection_exclusions_keep_saved_reasons(self):
        final = minimal_final(collection=[{"slug": "b", "url": "https://example.com/b", "status": "live"},
                                          {"slug": "offline", "url": "https://example.com/offline", "status": "blocked", "reason": "HTTP 403"}],
                              unselected_boards=[{"slug": "outside", "domain": "example.com", "weight_basis": "policy_floor"}])
        dom = self.dom(final)
        for key in ("weights-note", "grid-note"):
            for text in ("1 live board(s) outside", "outside", "1 not classed live", "HTTP 403"):
                self.assertIn(text, dom[key]["text"])
        self.assertIn("HTTP 403", dom["evidence"]["text"])
        self.assertIn("not selected for scoring", to_markdown(final))

    def test_warning_text_and_redirected_source_url_are_visible(self):
        notices = ["Dependency package versions were not recorded by the host.",
                   "Legacy saved visit contracts retained without migration: old.example.",
                   "</script><script>untrusted warning</script>"]
        final = minimal_final(warnings=notices,
                              collection=[{"slug": "b", "final_url": "https://example.com/final", "status": "live"}])
        dom = self.dom(final)
        for notice in notices:
            self.assertIn(notice, dom["warnings"]["text"])
        self.assertNotEqual(dom["warnings"]["style"].get("display"), "none")
        self.assertIn("https://example.com/final", dom["evidence"]["text"])
        self.assertEqual(to_html(final).count("</script>"), 2)


if __name__ == "__main__":
    unittest.main()
