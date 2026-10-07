from __future__ import annotations

import csv
import hashlib
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


def save_board(run, value):
    """Save honest synthetic source cells and their byte identity."""
    snapshot = {"synthetic": True, "rows": value.get("rows", [])}
    name = "snapshots/%s.json" % value["slug"]
    write(run / name, snapshot)
    value.update(method="direct", complete=True, snapshot=name,
                 snapshot_sha256=hashlib.sha256((run / name).read_bytes()).hexdigest())
    for index, row in enumerate(value.get("rows", [])):
        row["cell"] = "/rows/%d/quality" % index
    write(run / "leaderboards" / (value["slug"] + ".json"), value)


def save_dimensions(run, document):
    """Save declared test observations as explicit fabricated cell evidence."""
    name = "snapshots/dimensions.json"
    write(run / name, {"synthetic": True, "observations": document["observations"]})
    digest = hashlib.sha256((run / name).read_bytes()).hexdigest()
    for index, observation in enumerate(document["observations"]):
        observation.update(snapshot=name, snapshot_sha256=digest,
                           cell="/observations/%d/value" % index)
    write(run / "dimensions.json", document)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.project = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.project)

    def new_run(self):
        result = run_cli("new", "OCR API", "--synthetic", "--project", str(self.project))
        self.assertEqual(result.returncode, 0, result.stderr)
        run = Path(result.stdout.strip())
        self.assertTrue(str(run).startswith(str(self.project / ".ihav_space/ihav-leaderboards/runs")))
        self.assertIn(".gitignore", result.stderr)
        return run

    def mixed_run(self):
        run = self.new_run()
        shutil.copy(FIXTURES / "visits/huggingface.co.json", run / "visits")
        write(run / "boards.json", {"boards": [
            {"slug": slug, "domain": "huggingface.co", "status": "live",
             "final_url": "https://huggingface.co/" + slug}
            for slug in ("metric", "ranks")]})
        save_board(run, board("metric", [("A", 10), ("B", 20), ("C", 30)],
                              final_url="https://huggingface.co/metric"))
        save_board(run, board("ranks", [("A", 1), ("B", 2), ("C", 3)],
                              direction="lower_better", score_kind="rank_only",
                              final_url="https://huggingface.co/ranks"))
        write(run / "matches.json", {"candidates": [
            {"id": name, "name": name,
             "aliases": [{"board": slug, "name": name} for slug in ("metric", "ranks")]}
            for name in "ABC"]})
        result = run_cli("weigh", str(run))
        self.assertEqual(result.returncode, 0, result.stderr)
        return run

    def assert_metric_only_score(self, run, rank_status):
        final = json.loads((run / "final.json").read_text())
        boards = {item["slug"]: item for item in final["boards"]}
        self.assertEqual(boards["metric"]["status"], "scored")
        self.assertEqual(boards["metric"]["weight"], 1.0)
        self.assertEqual(boards["ranks"]["status"], rank_status)
        self.assertEqual(boards["ranks"]["weight"], 0.0)
        self.assertEqual(boards["ranks"]["quality_values"], {})
        self.assertEqual(boards["ranks"]["score_evidence"], {})
        self.assertEqual(final["counts"]["selected"], 2)
        self.assertEqual(final["counts"]["scored"], 1)
        candidates = {item["id"]: item for item in final["candidates"]}
        self.assertEqual(set(candidates), {"A", "B", "C"})
        for name, score in (("A", 0.0), ("B", 50.0), ("C", 100.0)):
            self.assertEqual(candidates[name]["final"], score)
            self.assertEqual(candidates[name]["scores"], {"metric": score})
            self.assertEqual(candidates[name]["confidence"], 1.0)
        receipt = json.loads((run / "run_state.json").read_text())["stages"]["score"]
        self.assertEqual(receipt["status"], "complete")
        self.assertEqual(set(receipt["outputs"]),
                         {"final.json", "leaderboard.md", "leaderboard.csv", "report.html"})
        result = run_cli("verify", str(run), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["current"])
        return boards

    def test_invalid_score_kind_rejects_mixed_run_without_score_outputs(self):
        cases = [(value, None) for value in
                 ("rank-only", "Score", "rank_only ", "", None, True, 1, 1.5, [], {}, ["score"])]
        cases.extend(("rank-only", status) for status in ("extract_failed", "unverified"))
        for value, status in cases:
            with self.subTest(score_kind=value, status=status):
                run = self.mixed_run()
                initial = run_cli("score", str(run))
                self.assertEqual(initial.returncode, 0, initial.stderr)
                previous = json.loads((run / "run_state.json").read_text())["stages"]["score"]
                self.assertEqual(previous["status"], "complete")
                path = run / "leaderboards/ranks.json"
                document = json.loads(path.read_text())
                document["score_kind"] = value
                if status is not None:
                    document.update(status=status, reason="Recorded extraction failure.")
                write(path, document)

                result = run_cli("score", str(run))
                self.assertEqual(result.returncode, 64, result.stderr)
                self.assertIn("score_kind", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                for name in ("final.json", "leaderboard.md", "leaderboard.csv", "report.html"):
                    self.assertFalse((run / name).exists(), name)
                state = json.loads((run / "run_state.json").read_text())
                self.assertEqual(state["stages"]["weigh"]["status"], "complete")
                failed = state["stages"]["score"]
                self.assertEqual(failed["status"], "failed")
                self.assertNotEqual(failed["generation"], previous["generation"])
                self.assertNotIn("outputs", failed)
                diagnostic = json.loads((run / "diagnostic.json").read_text())
                self.assertEqual(diagnostic["stage"], "score")
                self.assertEqual(diagnostic["exit_code"], 64)
                self.assertIn("score_kind", diagnostic["reason"])
                verified = run_cli("verify", str(run), "--json")
                self.assertEqual(verified.returncode, 2, verified.stderr)
                self.assertFalse(json.loads(verified.stdout)["current"])

    def test_missing_score_kind_keeps_metric_compatibility(self):
        run = self.mixed_run()
        path = run / "leaderboards/metric.json"
        document = json.loads(path.read_text())
        del document["score_kind"]
        write(path, document)
        result = run_cli("score", str(run))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_metric_only_score(run, "rank_only_unscored")

    def test_valid_rank_only_board_never_contributes_metric_scores(self):
        run = self.mixed_run()
        result = run_cli("score", str(run))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_metric_only_score(run, "rank_only_unscored")

    def test_rank_only_missing_provenance_remains_unverified(self):
        cases = (
            ("missing_method", "method", None, "Unknown or missing extraction method."),
            ("unknown_method", "method", "unsupported", "Unknown or missing extraction method."),
            ("missing_complete", "complete", None, "Extraction completeness is not explicitly true."),
            ("incomplete", "complete", False, "Extraction completeness is not explicitly true."),
            ("missing_snapshot", "snapshot", None, "No saved source snapshot."),
            ("missing_digest", "snapshot_sha256", None, "No valid source snapshot SHA-256."),
            ("invalid_digest", "snapshot_sha256", "invalid", "No valid source snapshot SHA-256."),
        )
        for case, field, value, reason in cases:
            with self.subTest(case=case):
                run = self.mixed_run()
                path = run / "leaderboards/ranks.json"
                document = json.loads(path.read_text())
                if value is None:
                    del document[field]
                else:
                    document[field] = value
                write(path, document)
                result = run_cli("score", str(run))
                self.assertEqual(result.returncode, 0, result.stderr)
                boards = self.assert_metric_only_score(run, "unverified")
                self.assertIn(reason, boards["ranks"]["reason"])

    def test_rank_only_missing_or_changed_snapshot_file_remains_unverified(self):
        for case in ("missing", "changed"):
            with self.subTest(case=case):
                run = self.mixed_run()
                snapshot = run / "snapshots/ranks.json"
                if case == "missing":
                    snapshot.unlink()
                    reason = "Saved source snapshot is missing."
                else:
                    snapshot.write_text("Changed synthetic rank source.", encoding="utf-8")
                    reason = "Saved source snapshot SHA-256 does not match."
                result = run_cli("score", str(run))
                self.assertEqual(result.returncode, 0, result.stderr)
                boards = self.assert_metric_only_score(run, "unverified")
                self.assertIn(reason, boards["ranks"]["reason"])

    def test_extraction_failure_presets_remain_reported_without_provenance(self):
        for status in ("extract_failed", "unverified"):
            with self.subTest(status=status):
                run = self.mixed_run()
                path = run / "leaderboards/ranks.json"
                document = json.loads(path.read_text())
                for field in ("method", "complete", "snapshot", "snapshot_sha256"):
                    del document[field]
                document.update(status=status, reason="Recorded extraction failure.")
                write(path, document)
                result = run_cli("score", str(run))
                self.assertEqual(result.returncode, 0, result.stderr)
                boards = self.assert_metric_only_score(run, status)
                self.assertEqual(boards["ranks"]["reason"], "Recorded extraction failure.")

    def test_full_offline_run(self):
        run = self.new_run()
        for domain in ("huggingface.co", "paperswithcode.com", "example-bench.org"):
            shutil.copy(FIXTURES / "visits" / ("%s.json" % domain), run / "visits")
        write(run / "boards.json", {"boards": [
            {"slug": "hf-ocr", "domain": "huggingface.co", "status": "live", "final_url": "https://huggingface.co/hf-ocr"},
            {"slug": "pwc-ocr", "domain": "paperswithcode.com", "status": "live", "final_url": "https://paperswithcode.com/pwc-ocr"},
            {"slug": "bench", "domain": "example-bench.org", "status": "live", "final_url": "https://example-bench.org/bench"},
            {"slug": "gone", "domain": "dead.example", "status": "dead"},
        ]})
        self.assertEqual(run_cli("weigh", str(run)).returncode, 0)
        weights = json.loads((run / "weights.json").read_text())
        self.assertEqual(len(weights["boards"]), 3)

        save_board(run, board("hf-ocr", [("A", 90), ("B", 80), ("C", 70)], final_url="https://huggingface.co/hf-ocr"))
        save_board(run, board("pwc-ocr", [("A", 5.0), ("B", 2.0), ("D", 9.0)], direction="lower_better", final_url="https://paperswithcode.com/pwc-ocr"))
        save_board(run, board("bench", [("A", 1), ("B", 2), ("C", 3)], score_kind="rank_only", final_url="https://example-bench.org/bench"))
        names = {"hf-ocr": "ABC", "pwc-ocr": "ABD", "bench": "ABC"}
        write(run / "matches.json", {"candidates": [
            {"id": n, "name": "Vendor " + n, "aliases": [{"board": s, "name": n} for s, ns in names.items() if n in ns]}
            for n in "ABCD"]})
        save_dimensions(run, {"registry": [
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
        self.assertEqual(rows[0], ["rank", "candidate", "final_score", "confidence", "price", "synthetic"])
        self.assertEqual(len(rows), 5)
        self.assertIn("rank_only_unscored", (run / "leaderboard.md").read_text())

    def test_all_rank_only_exits_2_with_diagnostic(self):
        run = self.new_run()
        shutil.copy(FIXTURES / "visits/example-bench.org.json", run / "visits")
        write(run / "boards.json", {"boards": [{"slug": "b", "domain": "example-bench.org", "status": "live", "url": "https://example-bench.org/b"}]})
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
        self.assertIn("ihav-leaderboards 0.3.0", result.stdout)


if __name__ == "__main__":
    unittest.main()
