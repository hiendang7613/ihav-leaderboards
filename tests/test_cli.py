from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import FIXTURES, SCRIPT, board


def run_cli(*args, cwd=None):
    return subprocess.run([sys.executable, str(SCRIPT)] + list(args), cwd=cwd,
                          capture_output=True, text=True, timeout=60)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class CliTests(unittest.TestCase):
    def setUp(self):
        self.project = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.project)

    def new_run(self):
        result = run_cli("new", "OCR API", "--project", str(self.project))
        self.assertEqual(result.returncode, 0, result.stderr)
        run = Path(result.stdout.strip())
        self.assertTrue(str(run).startswith(str(self.project / ".ihav_space/ihav-leaderboards/runs")))
        self.assertIn(".gitignore", result.stderr)
        return run

    def test_full_offline_run(self):
        run = self.new_run()
        for domain in ("huggingface.co", "paperswithcode.com", "example-bench.org"):
            shutil.copy(FIXTURES / "visits" / ("%s.json" % domain), run / "visits")
        write(run / "boards.json", {"boards": [
            {"slug": "hf-ocr", "domain": "huggingface.co", "status": "live"},
            {"slug": "pwc-ocr", "domain": "paperswithcode.com", "status": "live"},
            {"slug": "bench", "domain": "example-bench.org", "status": "live"},
            {"slug": "gone", "domain": "dead.example", "status": "dead"},
        ]})
        self.assertEqual(run_cli("weigh", str(run)).returncode, 0)
        weights = json.loads((run / "weights.json").read_text())
        self.assertEqual(len(weights["boards"]), 3)

        write(run / "leaderboards/hf-ocr.json", board("hf-ocr", [("A", 90), ("B", 80), ("C", 70)]))
        write(run / "leaderboards/pwc-ocr.json",
              board("pwc-ocr", [("A", 5.0), ("B", 2.0), ("D", 9.0)], direction="lower_better"))
        write(run / "leaderboards/bench.json", board("bench", [("A", 1), ("B", 2), ("C", 3)], score_kind="rank_only"))
        names = {"hf-ocr": "ABC", "pwc-ocr": "ABD", "bench": "ABC"}
        write(run / "matches.json", {"candidates": [
            {"id": n, "name": "Vendor " + n, "aliases": [{"board": s, "name": n} for s, ns in names.items() if n in ns]}
            for n in "ABCD"]})
        write(run / "dimensions.json", {"registry": [
            {"key": "price", "unit": "USD/1k pages", "type": "number", "direction": "lower_better", "context": "base"}],
            "observations": [
                {"id": "o1", "candidate": "A", "key": "price", "value": 10, "context": "base", "source_type": "official"},
                {"id": "o2", "candidate": "B", "key": "price", "value": 1, "context": "base", "source_type": "official"}]})

        result = run_cli("score", str(run))
        self.assertEqual(result.returncode, 0, result.stderr)
        final = json.loads((run / "final.json").read_text())
        status = {b["slug"]: b["status"] for b in final["boards"]}
        self.assertEqual(status["bench"], "rank_only_unscored")
        self.assertEqual(final["counts"]["scored"], 2)
        self.assertEqual(final["query"], "OCR API")
        self.assertIn("price", final["pareto"])
        rows = list(csv.reader(io.StringIO((run / "leaderboard.csv").read_text())))
        self.assertEqual(rows[0], ["rank", "candidate", "final_score", "confidence", "price"])
        self.assertEqual(len(rows), 5)
        self.assertIn("rank_only_unscored", (run / "leaderboard.md").read_text())

    def test_all_rank_only_exits_2_with_diagnostic(self):
        run = self.new_run()
        shutil.copy(FIXTURES / "visits/example-bench.org.json", run / "visits")
        write(run / "boards.json", {"boards": [{"slug": "b", "domain": "example-bench.org", "status": "live"}]})
        result = run_cli("weigh", str(run))
        self.assertEqual(result.returncode, 2)
        self.assertFalse((run / "weights.json").exists())
        self.assertEqual(json.loads((run / "diagnostic.json").read_text())["stage"], "weigh")

    def test_missing_input_exits_64(self):
        self.assertEqual(run_cli("score", str(self.project / "nope")).returncode, 64)

    def test_gitignore_with_ihav_space_has_no_warning(self):
        (self.project / ".gitignore").write_text(".ihav_space/\n")
        result = run_cli("new", "x", "--project", str(self.project))
        self.assertEqual(result.stderr, "")

    def test_doctor(self):
        result = run_cli("doctor", "--project", str(self.project))
        self.assertEqual(result.returncode, 0)
        self.assertIn("ihav-leaderboards 0.2.0", result.stdout)


if __name__ == "__main__":
    unittest.main()
