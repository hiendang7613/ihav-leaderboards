from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from ihav_leaderboards.render import to_html


def minimal_final(**extra):
    final = {
        "query": "OCR API",
        "counts": {"selected": 1, "scored": 1, "candidates_ranked": 1, "candidates_unranked": 0},
        "boards": [{"slug": "b", "status": "scored", "reason": "", "mass": 1, "weight": 1.0}],
        "candidates": [{"id": "a", "name": "A", "final": 100.0, "confidence": 1.0, "rank": 1, "scores": {"b": 100.0}}],
        "registry": [], "dimensions": {}, "pareto": {}, "notes": [],
    }
    final.update(extra)
    return final


def embedded_json(page):
    match = re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S)
    return json.loads(match.group(1))


class RenderTests(unittest.TestCase):
    def test_data_round_trips_and_title_is_escaped(self):
        page = to_html(minimal_final(query="<OCR> & co"))
        self.assertIn("<title>Best &lt;OCR&gt; &amp; co</title>", page)
        self.assertEqual(embedded_json(page)["query"], "<OCR> & co")

    def test_candidate_name_cannot_close_the_script_tag(self):
        hostile = "</script><script>alert(1)</script>"
        final = minimal_final()
        final["candidates"][0]["name"] = hostile
        page = to_html(final)
        self.assertEqual(page.count("</script>"), 2)
        self.assertEqual(embedded_json(page)["candidates"][0]["name"], hostile)

    def test_nonfinite_numbers_become_null(self):
        final = minimal_final()
        final["candidates"][0]["final"] = float("nan")
        self.assertIsNone(embedded_json(to_html(final))["candidates"][0]["final"])

    def test_template_uses_text_content_not_inner_html(self):
        page = to_html(minimal_final())
        self.assertNotIn("innerHTML", page)
        self.assertIn("textContent", page)

    def test_template_supports_light_and_dark(self):
        page = to_html(minimal_final())
        self.assertIn("prefers-color-scheme: dark", page)
        self.assertIn(':root[data-theme="dark"]', page)

    def test_synthetic_example_scores_and_renders(self):
        import subprocess
        import sys
        from helpers import SCRIPT
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        run = tmp / "run"
        shutil.copytree(ROOT / "examples/synthetic-ocr", run)
        for name in ("weights.json", "final.json", "report.html"):
            (run / name).unlink()
        self.assertEqual(subprocess.run([sys.executable, str(SCRIPT), "weigh", str(run)], capture_output=True).returncode, 0)
        self.assertEqual(subprocess.run([sys.executable, str(SCRIPT), "score", str(run)], capture_output=True).returncode, 0)
        data = embedded_json((run / "report.html").read_text(encoding="utf-8"))
        self.assertEqual(data["counts"]["scored"], 4)
        self.assertEqual(sorted(data["pareto"]), ["latency", "price"])
        status = {b["slug"]: b["status"] for b in data["boards"]}
        self.assertEqual(status["paperbench-rank"], "rank_only_unscored")


if __name__ == "__main__":
    unittest.main()
