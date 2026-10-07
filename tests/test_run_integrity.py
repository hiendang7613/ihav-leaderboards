from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import stat
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import ROOT, board, matches
from test_cli import run_cli, save_board, save_dimensions, write

from ihav_leaderboards import cli, receipts, runs


OUTPUTS = ("final.json", "leaderboard.md", "leaderboard.csv", "report.html")


def tree_identity(folder):
    return {path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in folder.rglob("*") if path.is_file()}


class RunIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.project = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.project)

    def prepare(self):
        created = run_cli("new", "Synthetic OCR", "--synthetic", "--project", str(self.project))
        self.assertEqual(created.returncode, 0, created.stderr)
        run = Path(created.stdout.strip())
        write(run / "boards.json", {"boards": [
            {"slug": "b", "domain": "one.example", "status": "live", "final_url": "https://one.example/b"},
            {"slug": "gone", "domain": "dead.example", "status": "dead", "reason": "HTTP 404"}]})
        write(run / "visits/one.example.json", {
            "contract_version": 2, "domain": "one.example", "kind": "estimate",
            "monthly_visits": 100, "source": {"name": "synthetic"}, "period": "2026-09"})
        value = board("b", [("A", 10), ("B", 20), ("C", 30)], final_url="https://one.example/b")
        save_board(run, value)
        write(run / "matches.json", matches("ABC", ["b"]))
        return run

    def ready(self):
        run = self.prepare()
        for stage in ("weigh", "score"):
            result = run_cli(stage, str(run))
            self.assertEqual(result.returncode, 0, result.stderr)
        return run

    def run_main(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return cli.main(list(args))

    def history_files(self, run, name):
        return list((run / ".history").glob("*/" + name))

    def test_complete_receipt_is_read_only_and_hashes_every_output(self):
        run = self.ready()
        before = tree_identity(run)
        result = run_cli("verify", str(run), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["current"])
        self.assertIn("no provider", json.loads(result.stdout)["scope"])
        self.assertEqual(tree_identity(run), before)
        state = runs.read_json(run / "run_state.json")
        score = state["stages"]["score"]
        self.assertEqual(set(score["outputs"]), set(OUTPUTS))
        for name, digest in score["outputs"].items():
            self.assertEqual(digest, hashlib.sha256((run / name).read_bytes()).hexdigest())
        self.assertIn("snapshots/b.json", score["inputs"])
        self.assertEqual(score["weigh_generation"], state["stages"]["weigh"]["generation"])

    def test_bundled_synthetic_example_has_current_read_only_receipts(self):
        run = ROOT / "examples/synthetic-ocr"
        before = tree_identity(run)
        result = run_cli("verify", str(run), "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["current"])
        self.assertTrue(runs.read_json(run / "final.json")["synthetic"])
        self.assertEqual(tree_identity(run), before)

    def test_failed_reweigh_archives_old_outputs_and_refuses_old_weights(self):
        run = self.ready()
        old = {name: (run / name).read_bytes() for name in ("weights.json",) + OUTPUTS}
        write(run / "visits/one.example.json", {"domain": "one.example", "kind": "rank_only",
                                             "contract_version": 2, "monthly_visits": None})
        result = run_cli("weigh", str(run))
        self.assertEqual(result.returncode, 2, result.stderr)
        for name, content in old.items():
            self.assertFalse((run / name).exists(), name)
            self.assertTrue(any(path.read_bytes() == content for path in self.history_files(run, name)))
        self.assertEqual(run_cli("score", str(run)).returncode, 2)
        self.assertEqual(run_cli("verify", str(run)).returncode, 2)

    def test_verify_refuses_writer_invalidation_after_its_initial_state_read(self):
        for stage, config in (("weigh", {"top_n": 32}), ("score", {})):
            with self.subTest(stage=stage):
                run = self.ready()
                old_outputs = {name: (run / name).read_bytes()
                               for name in ("weights.json",) + OUTPUTS}
                reader_started = threading.Event()
                writer_invalidated = threading.Event()
                release_writer = threading.Event()
                errors = []
                real_read = receipts.read_state
                real_archive = receipts.archive_outputs

                def read_before_invalidation(folder):
                    state = real_read(folder)
                    if threading.current_thread() is threading.main_thread() and not reader_started.is_set():
                        reader_started.set()
                        if not writer_invalidated.wait(5):
                            raise AssertionError("Writer did not commit its running receipt.")
                    return state

                def pause_before_archival(*args, **kwargs):
                    writer_invalidated.set()
                    if not release_writer.wait(10):
                        raise AssertionError("Reader did not release the paused writer.")
                    return real_archive(*args, **kwargs)

                def writer():
                    try:
                        if not reader_started.wait(5):
                            raise AssertionError("Reader did not capture the complete receipt.")
                        with runs.run_lock(run):
                            receipts.begin_stage(run, stage, config)
                    except BaseException as exc:
                        errors.append(exc)

                with patch("ihav_leaderboards.receipts.read_state", side_effect=read_before_invalidation), \
                        patch("ihav_leaderboards.receipts.archive_outputs", side_effect=pause_before_archival):
                    thread = threading.Thread(target=writer)
                    thread.start()
                    try:
                        stdout, stderr = io.StringIO(), io.StringIO()
                        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                            code = cli.main(["verify", str(run), "--json"])
                        current_state = real_read(run)
                        self.assertEqual(current_state["stages"][stage]["status"], "running")
                        for name, content in old_outputs.items():
                            self.assertEqual((run / name).read_bytes(), content, name)
                        result = json.loads(stdout.getvalue())
                        self.assertEqual(code, 2, stdout.getvalue() + stderr.getvalue())
                        self.assertFalse(result["current"])
                        self.assertTrue(result["issues"])
                    finally:
                        release_writer.set()
                        thread.join(11)
                self.assertFalse(thread.is_alive(), "Paused writer was not joined.")
                self.assertEqual(errors, [])

    def test_failed_rescore_keeps_per_board_reason_without_public_stale_report(self):
        run = self.ready()
        old = (run / "final.json").read_bytes()
        path = run / "leaderboards/b.json"
        value = runs.read_json(path)
        for row in value["rows"]:
            row["verified"] = False
        write(path, value)
        result = run_cli("score", str(run))
        self.assertEqual(result.returncode, 2, result.stderr)
        for name in OUTPUTS:
            self.assertFalse((run / name).exists(), name)
        self.assertTrue(any(path.read_bytes() == old for path in self.history_files(run, "final.json")))
        diagnostic = runs.read_json(run / "diagnostic.json")
        self.assertEqual(diagnostic["boards"][0]["status"], "dropped_too_few")
        self.assertIn("0 distinct verified scores", diagnostic["boards"][0]["reason"])

    def test_changed_visits_refuse_score_until_new_weigh(self):
        run = self.ready()
        item = runs.read_json(run / "visits/one.example.json")
        item["monthly_visits"] = 101
        write(run / "visits/one.example.json", item)
        result = run_cli("score", str(run))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("inputs changed", result.stderr)
        self.assertFalse((run / "final.json").exists())
        self.assertEqual(run_cli("weigh", str(run)).returncode, 0)
        self.assertEqual(run_cli("score", str(run)).returncode, 0)
        self.assertEqual(run_cli("verify", str(run)).returncode, 0)

    def test_changed_dependency_record_invalidates_downstream(self):
        run = self.ready()
        request = runs.read_json(run / "request.json")
        request["dependencies"] = {"ihav-web-visit-counter": {"version": "test-version"}}
        write(run / "request.json", request)
        self.assertEqual(run_cli("verify", str(run)).returncode, 2)
        self.assertEqual(run_cli("score", str(run)).returncode, 2)

    def test_added_discovery_file_invalidates_weigh(self):
        run = self.ready()
        write(run / "discovery/child.json", {"run_id": "saved-child", "request_key": "stable-key"})
        self.assertEqual(run_cli("verify", str(run)).returncode, 2)

    def test_runtime_fingerprint_change_is_not_current(self):
        run = self.ready()
        with patch("ihav_leaderboards.receipts.runtime_identity", return_value={"version": "new", "code_sha256": "changed"}):
            self.assertEqual(self.run_main("verify", str(run)), 2)

    def test_runtime_identity_ignores_checkout_line_endings(self):
        package = Path(receipts.__file__).resolve().parent
        crlf = self.project / "crlf"
        crlf.mkdir()
        for path in list(package.glob("*.py")) + list(package.glob("*.html")):
            lf = path.read_bytes().replace(b"\r\n", b"\n")
            (crlf / path.name).write_bytes(lf.replace(b"\n", b"\r\n"))
        self.assertEqual(receipts.code_digest(crlf), receipts.code_digest(package))
        (crlf / "cli.py").write_bytes(b"# changed\r\n" + (crlf / "cli.py").read_bytes())
        self.assertNotEqual(receipts.code_digest(crlf), receipts.code_digest(package))

    def test_changed_source_bytes_are_unverified(self):
        run = self.ready()
        (run / "snapshots/b.json").write_text("Changed fixture source")
        self.assertEqual(run_cli("verify", str(run)).returncode, 2)
        result = run_cli("score", str(run))
        self.assertEqual(result.returncode, 2, result.stderr)
        diagnostic = runs.read_json(run / "diagnostic.json")
        self.assertEqual(diagnostic["boards"][0]["status"], "unverified")
        self.assertIn("SHA-256 does not match", diagnostic["boards"][0]["reason"])

    def test_source_url_mismatch_does_not_score_other_source(self):
        run = self.prepare()
        item = runs.read_json(run / "leaderboards/b.json")
        item["final_url"] = "https://other.example/b"
        write(run / "leaderboards/b.json", item)
        self.assertEqual(run_cli("weigh", str(run)).returncode, 0)
        self.assertEqual(run_cli("score", str(run)).returncode, 2)
        self.assertIn("differs from collected source", runs.read_json(run / "diagnostic.json")["boards"][0]["reason"])

    def test_missing_saved_cell_does_not_use_declared_verified_flag(self):
        run = self.prepare()
        item = runs.read_json(run / "leaderboards/b.json")
        del item["rows"][2]["cell"]
        write(run / "leaderboards/b.json", item)
        self.assertEqual(run_cli("weigh", str(run)).returncode, 0)
        self.assertEqual(run_cli("score", str(run)).returncode, 2)
        self.assertIn("2 distinct verified scores", runs.read_json(run / "diagnostic.json")["boards"][0]["reason"])

    def test_evidence_cannot_traverse_outside_run(self):
        run = self.prepare()
        item = runs.read_json(run / "leaderboards/b.json")
        item["snapshot"] = "../../outside.txt"
        write(run / "leaderboards/b.json", item)
        self.assertEqual(run_cli("weigh", str(run)).returncode, 0)
        result = run_cli("score", str(run))
        self.assertEqual(result.returncode, 64)
        self.assertIn("stay inside", result.stderr)

    def test_malformed_boards_exit_64_without_traceback_or_stale_outputs(self):
        run = self.ready()
        write(run / "boards.json", [])
        result = run_cli("weigh", str(run))
        self.assertEqual(result.returncode, 64, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((run / "weights.json").exists())
        self.assertFalse((run / "report.html").exists())
        verify = run_cli("verify", str(run), "--json")
        self.assertEqual(verify.returncode, 64)
        self.assertFalse(json.loads(verify.stdout)["current"])

    def test_unknown_counter_contract_is_rejected_not_treated_as_estimate(self):
        run = self.ready()
        item = runs.read_json(run / "visits/one.example.json")
        item["contract_version"] = 999
        write(run / "visits/one.example.json", item)
        result = run_cli("weigh", str(run))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("Unsupported visit contract_version", result.stderr)
        self.assertFalse((run / "weights.json").exists())
        verify = run_cli("verify", str(run), "--json")
        self.assertEqual(verify.returncode, 2)
        self.assertEqual(json.loads(verify.stdout)["exit_code"], 2)

    def test_domainless_child_error_is_retained_and_uses_policy_floor(self):
        run = self.prepare()
        collection = runs.read_json(run / "boards.json")
        collection["boards"].append({"slug": "blocked", "domain": "blocked.example", "status": "live",
                                     "final_url": "https://blocked.example/b"})
        write(run / "boards.json", collection)
        error = {"contract_version": 2, "error": {"code": "blocked", "notes": ["HTTP 403"]}}
        write(run / "visits/blocked.example.json", error)
        original = (run / "visits/blocked.example.json").read_bytes()
        self.assertEqual(run_cli("weigh", str(run)).returncode, 0)
        weights = runs.read_json(run / "weights.json")
        entry = next(item for item in weights["boards"] if item["slug"] == "blocked")
        self.assertEqual(entry["visit_error"]["code"], "blocked")
        self.assertEqual(entry["weight_basis"], "floor+domain_split(1)")
        self.assertIsNone(entry["monthly_visits"])
        self.assertEqual((run / "visits/blocked.example.json").read_bytes(), original)

    def test_visit_filename_mismatch_is_bad_input(self):
        run = self.prepare()
        item = runs.read_json(run / "visits/one.example.json")
        item["domain"] = "other.example"
        write(run / "visits/one.example.json", item)
        self.assertEqual(run_cli("weigh", str(run)).returncode, 64)

    def test_legacy_counter_output_is_labeled_without_rewriting_child(self):
        run = self.prepare()
        item = runs.read_json(run / "visits/one.example.json")
        del item["contract_version"]
        write(run / "visits/one.example.json", item)
        original = (run / "visits/one.example.json").read_bytes()
        self.assertEqual(run_cli("weigh", str(run)).returncode, 0)
        weights = runs.read_json(run / "weights.json")
        self.assertEqual(weights["dependencies"]["visit_contracts"]["one.example"]["compatibility"], "legacy_unversioned")
        self.assertEqual((run / "visits/one.example.json").read_bytes(), original)

    def test_synthetic_fixture_is_explicit_in_every_saved_score(self):
        run = self.ready()
        final = runs.read_json(run / "final.json")
        self.assertTrue(final["synthetic"])
        self.assertIn("Synthetic example", (run / "leaderboard.md").read_text())
        self.assertIn("not live benchmark evidence", (run / "leaderboard.md").read_text())
        self.assertIn("Synthetic", (run / "report.html").read_text())
        self.assertEqual(final["collection"][1]["status"], "dead")

    def test_render_refuses_changed_final_bytes(self):
        run = self.ready()
        final = runs.read_json(run / "final.json")
        final["candidates"][0]["final"] = 0
        write(run / "final.json", final)
        result = run_cli("render", str(run))
        self.assertEqual(result.returncode, 2)
        self.assertIn("final.json", result.stderr)

    def test_render_can_rebuild_missing_html_from_current_other_outputs(self):
        run = self.ready()
        (run / "report.html").unlink()
        self.assertEqual(run_cli("verify", str(run)).returncode, 2)
        result = run_cli("render", str(run))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(run_cli("verify", str(run)).returncode, 0)

    def test_lock_refuses_second_writer_without_changing_saved_stage(self):
        run = self.ready()
        before = tree_identity(run)
        with runs.run_lock(run):
            result = run_cli("weigh", str(run))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("Another writer", result.stderr)
        self.assertEqual(tree_identity(run), before)

    def test_partial_publication_never_has_current_receipt_and_is_recoverable(self):
        run = self.ready()
        replace = os.replace
        failed = []

        def fail_one(source, target):
            source = Path(source)
            if source.parent.name.startswith(".publish-") and source.name == "leaderboard.csv" and not failed:
                failed.append(True)
                raise OSError("simulated storage failure")
            return replace(source, target)

        with patch("ihav_leaderboards.receipts.os.replace", side_effect=fail_one):
            self.assertEqual(self.run_main("score", str(run)), 1)
        self.assertTrue(failed)
        self.assertEqual(run_cli("verify", str(run)).returncode, 2)
        self.assertEqual(runs.read_json(run / "run_state.json")["stages"]["score"]["status"], "failed")
        for name in OUTPUTS:
            self.assertFalse((run / name).exists(), name)
        self.assertTrue(self.history_files(run, "final.json"))
        self.assertFalse(list(run.glob(".publish-*")))

    def test_input_drift_during_computation_refuses_publication(self):
        run = self.ready()
        real = cli.to_markdown

        def change_input(final):
            (run / "snapshots/b.json").write_text("changed while rendering formats")
            return real(final)

        with patch("ihav_leaderboards.cli.to_markdown", side_effect=change_input):
            self.assertEqual(self.run_main("score", str(run)), 2)
        self.assertFalse((run / "final.json").exists())
        self.assertEqual(run_cli("verify", str(run)).returncode, 2)

    def test_strict_json_rejects_duplicate_and_nonfinite_values(self):
        run = self.prepare()
        for content in ('{"boards":[],"boards":[]}', '{"boards":NaN}'):
            with self.subTest(content=content):
                (run / "boards.json").write_text(content)
                result = run_cli("weigh", str(run))
                self.assertEqual(result.returncode, 64, result.stderr)

    def test_atomic_single_file_failure_preserves_original_and_cleans_temporary(self):
        target = self.project / "value.json"
        runs.write_json(target, {"old": True})
        with patch("ihav_leaderboards.runs.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                runs.write_json(target, {"new": True})
        self.assertEqual(runs.read_json(target), {"old": True})
        self.assertFalse(list(self.project.glob(".tmp-*")))

    @unittest.skipIf(os.name == "nt", "POSIX file modes")
    def test_outputs_get_ordinary_permissions_from_the_umask(self):
        previous = os.umask(0o022)
        try:
            run = self.ready()
        finally:
            os.umask(previous)
        for name in ("weights.json", "run_state.json") + OUTPUTS:
            self.assertEqual(stat.S_IMODE((run / name).stat().st_mode), 0o644, name)

    def test_positive_top_is_required_and_usage_errors_are_64(self):
        run = self.prepare()
        for argument in ("0", "-1", "bad"):
            with self.subTest(argument=argument):
                self.assertEqual(run_cli("weigh", str(run), "--top", argument).returncode, 64)



    def test_collection_redirect_host_mismatch_is_bad_input(self):
        run = self.prepare()
        collection = runs.read_json(run / "boards.json")
        collection["boards"][0].update(url="https://one.example/original", final_url="https://other.example/redirect")
        write(run / "boards.json", collection)
        result = run_cli("weigh", str(run))
        self.assertEqual(result.returncode, 64, result.stderr)
        self.assertIn("host differs", result.stderr)
        self.assertFalse((run / "weights.json").exists())

    def test_host_normalization_preserves_subdomain_identity(self):
        run = self.prepare()
        original = runs.read_json(run / "boards.json")
        for host in ("ONE.EXAMPLE.", "www.one.example", "WWW.ONE.EXAMPLE."):
            with self.subTest(host=host):
                collection = json.loads(json.dumps(original))
                collection["boards"][0]["domain"] = host
                collection["boards"][0]["final_url"] = "https://WWW.One.Example./b"
                write(run / "boards.json", collection)
                result = run_cli("weigh", str(run))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(runs.read_json(run / "weights.json")["boards"][0]["domain"], "one.example")
        original["boards"][0]["final_url"] = "https://sub.one.example/b"
        write(run / "boards.json", original)
        self.assertEqual(run_cli("weigh", str(run)).returncode, 64)

    def test_mixed_counter_error_and_result_never_uses_visit_number(self):
        run = self.prepare()
        item = runs.read_json(run / "visits/one.example.json")
        item["error"] = {"code": "blocked"}
        item["monthly_visits"] = 1000000
        write(run / "visits/one.example.json", item)
        result = run_cli("weigh", str(run))
        self.assertEqual(result.returncode, 64, result.stderr)
        self.assertIn("mutually exclusive", result.stderr)
        self.assertFalse((run / "weights.json").exists())
        self.assertEqual(run_cli("verify", str(run), "--json").returncode, 64)

    def price_document(self, value=1.5):
        return {"registry": [{"key": "price", "type": "number", "direction": "lower_better", "context": "base"}],
                "observations": [{"id": "price-A", "candidate": "A", "key": "price", "value": value,
                                  "context": "base", "source_type": "official", "url": "https://one.example/price"}]}

    def test_official_dimension_requires_saved_hash_and_cell(self):
        run = self.prepare()
        self.assertEqual(run_cli("weigh", str(run)).returncode, 0)
        document = self.price_document()
        write(run / "dimensions.json", document)
        result = run_cli("score", str(run))
        self.assertEqual(result.returncode, 64, result.stderr)
        self.assertFalse((run / "final.json").exists())
        save_dimensions(run, document)
        for field in ("cell", "snapshot_sha256", "snapshot"):
            with self.subTest(field=field):
                broken = json.loads(json.dumps(document))
                del broken["observations"][0][field]
                write(run / "dimensions.json", broken)
                self.assertEqual(run_cli("score", str(run)).returncode, 64)
        document["observations"][0].update(cell="", locator="/observations/0/value")
        write(run / "dimensions.json", document)
        self.assertEqual(run_cli("score", str(run)).returncode, 0)
        self.assertEqual(run_cli("verify", str(run)).returncode, 0)
        final = runs.read_json(run / "final.json")
        self.assertIn("snapshots/dimensions.json", final["publication"]["source_sha256"])
        self.assertEqual(final["dimensions"]["A"]["price"]["cell"], "/observations/0/value")

    def test_changed_dimension_source_refuses_publication(self):
        run = self.prepare()
        save_dimensions(run, self.price_document())
        self.assertEqual(run_cli("weigh", str(run)).returncode, 0)
        self.assertEqual(run_cli("score", str(run)).returncode, 0)
        (run / "snapshots/dimensions.json").write_text("changed declared price source")
        self.assertEqual(run_cli("verify", str(run)).returncode, 2)
        result = run_cli("score", str(run))
        self.assertEqual(result.returncode, 64, result.stderr)
        self.assertIn("snapshot hash mismatch", result.stderr)
        self.assertFalse((run / "final.json").exists())

    def test_leaderboard_dimension_can_use_validated_board_snapshot(self):
        run = self.prepare()
        value = runs.read_json(run / "leaderboards/b.json")
        value["rows"][0]["price"] = 1.5
        save_board(run, value)
        document = self.price_document()
        observation = document["observations"][0]
        observation.update(source_type="leaderboard", board="b", cell="/rows/0/price",
                           snapshot=value["snapshot"], snapshot_sha256=value["snapshot_sha256"].upper())
        write(run / "dimensions.json", document)
        self.assertEqual(run_cli("weigh", str(run)).returncode, 0)
        result = run_cli("score", str(run))
        self.assertEqual(result.returncode, 0, result.stderr)
        chosen = runs.read_json(run / "final.json")["dimensions"]["A"]["price"]
        self.assertEqual(chosen["snapshot"], "snapshots/b.json")
        self.assertEqual(chosen["cell"], "/rows/0/price")
        self.assertEqual(run_cli("verify", str(run)).returncode, 0)

    def test_null_dimension_stays_missing_without_fabricated_evidence(self):
        run = self.prepare()
        write(run / "dimensions.json", self.price_document(value=None))
        self.assertEqual(run_cli("weigh", str(run)).returncode, 0)
        result = run_cli("score", str(run))
        self.assertEqual(result.returncode, 0, result.stderr)
        final = runs.read_json(run / "final.json")
        self.assertEqual(final["dimensions"], {})
        self.assertEqual(final["pareto"]["price"]["plotted"], 0)

    def test_pre_attempt_copy_failure_preserves_originals_and_truthful_inventory(self):
        run = self.ready()
        originals = {name: (run / name).read_bytes() for name in OUTPUTS}
        real = shutil.copyfile

        def fail_csv(source, target, *args, **kwargs):
            if Path(source).name == "leaderboard.csv":
                raise OSError("persistent archive copy failure")
            return real(source, target, *args, **kwargs)

        with patch("ihav_leaderboards.receipts.shutil.copyfile", side_effect=fail_csv):
            self.assertEqual(self.run_main("score", str(run)), 1)
        self.assertEqual(runs.read_json(run / "run_state.json")["stages"]["score"]["status"], "failed")
        diagnostic = runs.read_json(run / "diagnostic.json")
        self.assertIn("persistent archive copy failure", diagnostic["reason"])
        self.assertIn("persistent archive copy failure", diagnostic["cleanup_error"])
        self.assertEqual(run_cli("verify", str(run)).returncode, 2)
        for name, content in originals.items():
            self.assertEqual((run / name).read_bytes(), content)
        manifests = list((run / ".history").glob("*/manifest.json"))
        self.assertTrue(manifests)
        for path in manifests:
            manifest = runs.read_json(path)
            self.assertEqual(manifest["status"], "copy_failed")
            self.assertEqual(manifest["removed_from_root"], [])
            self.assertEqual(set(manifest["expected_files"]), set(OUTPUTS))
            self.assertNotIn("leaderboard.csv", manifest["files"])
            for name, digest in manifest["files"].items():
                self.assertEqual(runs.file_digest(path.parent / name), digest)

    def test_pre_attempt_removal_failure_leaves_verified_backup_and_failed_receipt(self):
        run = self.ready()
        originals = {name: (run / name).read_bytes() for name in OUTPUTS}
        real = Path.unlink

        def fail_csv(path, *args, **kwargs):
            if path == run / "leaderboard.csv":
                raise OSError("persistent root removal failure")
            return real(path, *args, **kwargs)

        with patch("pathlib.Path.unlink", new=fail_csv):
            self.assertEqual(self.run_main("score", str(run)), 1)
        self.assertEqual(runs.read_json(run / "run_state.json")["stages"]["score"]["status"], "failed")
        self.assertIn("persistent root removal failure", runs.read_json(run / "diagnostic.json")["reason"])
        self.assertEqual(run_cli("verify", str(run)).returncode, 2)
        found = False
        for path in (run / ".history").glob("*/manifest.json"):
            manifest = runs.read_json(path)
            if set(manifest["files"]) == set(OUTPUTS):
                found = True
                self.assertEqual(manifest["status"], "removal_incomplete")
                for name, content in originals.items():
                    self.assertEqual((path.parent / name).read_bytes(), content)
        self.assertTrue(found)
        self.assertEqual((run / "leaderboard.csv").read_bytes(), originals["leaderboard.csv"])

    def test_coordinated_boolean_generation_is_malformed_not_current(self):
        run = self.ready()
        state = runs.read_json(run / "run_state.json")
        state["stages"]["weigh"]["generation"] = False
        state["stages"]["score"]["generation"] = False
        state["stages"]["score"]["weigh_generation"] = False
        write(run / "run_state.json", state)
        result = run_cli("verify", str(run), "--json")
        self.assertEqual(result.returncode, 64, result.stderr)
        self.assertFalse(json.loads(result.stdout)["current"])
        self.assertIn("generation", json.loads(result.stdout)["error"])

    def test_receipt_shape_errors_are_64_before_freshness_check(self):
        run = self.ready()
        original = runs.read_json(run / "run_state.json")
        changes = [
            ("input_digest", lambda s: s["stages"]["score"]["inputs"].update({"request.json": 7})),
            ("output_digest", lambda s: s["stages"]["score"]["outputs"].update({"final.json": False})),
            ("runtime_hash", lambda s: s["stages"]["score"]["runtime"].update({"code_sha256": "bad"})),
            ("config", lambda s: s["stages"]["weigh"]["config"].update({"top_n": True})),
            ("timestamp", lambda s: s["stages"]["score"].update({"completed_at": "2026-10-06"})),
            ("container", lambda s: s["stages"].update({"score": []})),
        ]
        for name, change in changes:
            with self.subTest(field=name):
                state = json.loads(json.dumps(original))
                change(state)
                write(run / "run_state.json", state)
                result = run_cli("verify", str(run), "--json")
                self.assertEqual(result.returncode, 64, result.stderr)
                self.assertFalse(json.loads(result.stdout)["current"])

    def test_valid_incomplete_receipts_are_stale_not_malformed(self):
        run = self.ready()
        original = runs.read_json(run / "run_state.json")
        for status in ("running", "failed", "rendering", "invalidated"):
            with self.subTest(status=status):
                state = json.loads(json.dumps(original))
                if status == "invalidated":
                    state["stages"]["score"] = {"status": status, "reason": "new weigh attempt"}
                else:
                    state["stages"]["score"]["status"] = status
                    if status == "failed":
                        state["stages"]["score"]["reason"] = "simulated failure"
                write(run / "run_state.json", state)
                result = run_cli("verify", str(run), "--json")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(json.loads(result.stdout)["current"])


    def test_leaderboard_dimension_rejects_unrelated_explicit_snapshot(self):
        run = self.prepare()
        document = self.price_document(value=999)
        save_dimensions(run, document)
        document["observations"][0].update(source_type="leaderboard", board="b")
        write(run / "dimensions.json", document)
        self.assertEqual(run_cli("weigh", str(run)).returncode, 0)
        result = run_cli("score", str(run))
        self.assertEqual(result.returncode, 64, result.stderr)
        self.assertIn("differs from referenced board", result.stderr)
        self.assertFalse((run / "final.json").exists())


    def test_render_archive_failure_preserves_prior_receipt_and_can_retry(self):
        run = self.ready()
        original = (run / "report.html").read_bytes()
        real = shutil.copyfile

        def fail_html(source, target, *args, **kwargs):
            if Path(source).name == "report.html":
                raise OSError("persistent render archive failure")
            return real(source, target, *args, **kwargs)

        with patch("ihav_leaderboards.receipts.shutil.copyfile", side_effect=fail_html):
            self.assertEqual(self.run_main("render", str(run)), 1)
        self.assertEqual((run / "report.html").read_bytes(), original)
        self.assertEqual(runs.read_json(run / "run_state.json")["stages"]["score"]["status"], "complete")
        self.assertIn("persistent render archive failure", runs.read_json(run / "diagnostic.json")["reason"])
        self.assertEqual(len(list((run / ".history").glob("*/manifest.json"))), 1)
        self.assertEqual(run_cli("verify", str(run)).returncode, 0)
        self.assertEqual(run_cli("render", str(run)).returncode, 0)
        self.assertEqual(run_cli("verify", str(run)).returncode, 0)

    def test_archive_rejects_external_history_symlink_before_any_copy(self):
        run = self.ready()
        originals = {name: (run / name).read_bytes() for name in OUTPUTS}
        outside = self.project / "outside-history"
        outside.mkdir()
        (run / ".history").symlink_to(outside, target_is_directory=True)
        result = run_cli("score", str(run))
        self.assertEqual(result.returncode, 64, result.stderr)
        self.assertEqual(list(outside.iterdir()), [])
        for name, content in originals.items():
            self.assertEqual((run / name).read_bytes(), content)
        self.assertEqual(runs.read_json(run / "run_state.json")["stages"]["score"]["status"], "failed")
        self.assertIn("history", runs.read_json(run / "diagnostic.json")["reason"])
        self.assertEqual(run_cli("verify", str(run)).returncode, 2)


    def test_render_commit_failure_restores_old_hash_and_allows_retry(self):
        run = self.ready()
        original = runs.read_json(run / "run_state.json")["stages"]["score"]
        real_write = cli.write_json
        real_html = cli.to_html
        failed = []

        def fail_commit(path, value):
            if path == run / "run_state.json" and value["stages"]["score"]["status"] == "complete" and not failed:
                failed.append(True)
                raise OSError("simulated complete receipt write failure")
            return real_write(path, value)

        def changed_html(final):
            return real_html(final) + "<!-- rebuilt HTML -->"

        with patch("ihav_leaderboards.cli.write_json", side_effect=fail_commit), patch("ihav_leaderboards.cli.to_html", side_effect=changed_html):
            self.assertEqual(self.run_main("render", str(run)), 1)
        state = runs.read_json(run / "run_state.json")
        self.assertEqual(state["stages"]["score"], original)
        self.assertEqual(runs.read_json(run / "diagnostic.json")["reason"], "simulated complete receipt write failure")
        self.assertFalse((run / "report.html").exists())
        self.assertEqual(run_cli("verify", str(run)).returncode, 2)
        self.assertEqual(run_cli("render", str(run)).returncode, 0)
        self.assertEqual(run_cli("verify", str(run)).returncode, 0)

if __name__ == "__main__":
    unittest.main()
