"""Deterministic local stages; no network, installation or provider calls.

Exit 0: operation succeeded; 2: busy run, no result, stale or incompatible saved dependency;
64: malformed input; 1: local I/O failed. Verification is read-only.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .dimensions import choose, pareto_charts
from .receipts import (
    STATE_NAME, StaleRunError, archive_outputs, begin_stage, check_stage, fail_stage,
    input_digests, publish, read_state, runtime_identity, verify_run,
)
from .render import to_html
from .runs import (
    SCHEMA_VERSION, DependencyContractError, RunBusyError, RunInputError, create_run, file_digest,
    gitignore_warning, json_text, object_file, read_visits, run_lock, write_json, write_text,
)
from .scoring import NoScoreError, merge
from .tables import to_csv, to_markdown
from .validation import (
    boards_file, dependency_summary, dimensions_file, extraction_files, matches_file,
    report_warnings, request_file,
)
from .weights import TOP_N, NoWeightError, allocate

EXIT_OK, EXIT_NO_RESULT, EXIT_INPUT, EXIT_IO = 0, 2, 64, 1


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise RunInputError(message)


def cmd_new(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    run = create_run(project, args.query, synthetic=args.synthetic)
    print(run)
    warning = gitignore_warning(project)
    if warning:
        print(warning, file=sys.stderr)
    return EXIT_OK


def _run_stage(args: argparse.Namespace, stage: str, operation: Any, config: Dict[str, Any]) -> int:
    run = Path(args.run).resolve()
    with run_lock(run):
        try:
            attempt = begin_stage(run, stage, config)
            operation(run, attempt)
            return EXIT_OK
        except (NoWeightError, NoScoreError, StaleRunError, DependencyContractError) as exc:
            reason, code, boards = str(exc), EXIT_NO_RESULT, getattr(exc, "boards", None)
        except (RunInputError, KeyError, TypeError, ValueError, OverflowError) as exc:
            reason, code, boards = str(exc), EXIT_INPUT, None
        except OSError as exc:
            reason, code, boards = str(exc), EXIT_IO, None
        try:
            fail_stage(run, stage, reason, code, boards=boards, config=config)
        except (OSError, RunInputError, StaleRunError) as diagnostic_error:
            print("Failure recording/cleanup was incomplete: %s" % diagnostic_error, file=sys.stderr)
        print("%s: %s" % ("Input error" if code == EXIT_INPUT else "Stage failed", reason), file=sys.stderr)
        return code


def cmd_weigh(args: argparse.Namespace) -> int:
    def operation(run: Path, attempt: Dict[str, Any]) -> None:
        if args.top < 1:
            raise RunInputError("--top must be a positive integer.")
        request = request_file(run)
        inputs = input_digests(run, "weigh")
        boards = boards_file(run)
        visits = read_visits(run)
        weights = allocate(boards, visits, top_n=args.top)
        weights["dependencies"] = dependency_summary(request, visits)
        weights["warnings"] = report_warnings(request, weights["dependencies"])
        weights["collection"] = boards  # Non-live sources remain report-only.
        publish(run, "weigh", attempt, inputs, {"weights.json": json_text(weights)})
        selected = sum(1 for entry in weights["boards"] if entry["selected"])
        print("Selected %d of %d live leaderboards. Floor weight used for %d domain(s)."
              % (selected, len(weights["boards"]), len(weights["floor_domains"])))
    return _run_stage(args, "weigh", operation, {"top_n": args.top})


def cmd_score(args: argparse.Namespace) -> int:
    def operation(run: Path, attempt: Dict[str, Any]) -> None:
        weigh_receipt = check_stage(run, "weigh")
        inputs = input_digests(run, "score")
        request = request_file(run)
        collection = boards_file(run)
        by_slug = {board["slug"]: board for board in collection}
        weights = object_file(run / "weights.json")
        matches = matches_file(run)
        boards = extraction_files(run)
        for candidate in matches["candidates"]:
            for alias in candidate.get("aliases", []):
                if alias["board"] not in by_slug:
                    raise RunInputError("Alias board is absent from collection: %s." % alias["board"])
        for board in boards:
            source = by_slug.get(board["slug"])
            if source is None:
                raise RunInputError("Extracted board is absent from collection: %s." % board["slug"])
            expected_url = source.get("final_url") or source.get("url")
            if expected_url and board.get("status") not in ("extract_failed", "unverified"):
                if board.get("final_url") != expected_url:
                    board.update(status="unverified", reason="Extraction final_url differs from collected source.")
            elif not expected_url and not request.get("synthetic", False):
                board.update(status="unverified", reason="Collection has no source URL to bind extraction.")
        final = merge(boards, weights, matches)
        source_names = {Path(board["snapshot"]).as_posix() for board in boards
                        if isinstance(board.get("snapshot"), str)}
        registry, chosen = [], {"values": {}, "conflicts": [], "out_of_context": 0}
        if (run / "dimensions.json").exists():
            dims = dimensions_file(run, {candidate["id"] for candidate in matches["candidates"]}, set(by_slug),
                                   {board["slug"]: board for board in boards})
            source_names.update(Path(observation["snapshot"]).as_posix() for observation in dims["observations"]
                                if isinstance(observation.get("snapshot"), str))
            registry = dims["registry"]
            board_weights = {board["slug"]: board["weight"] for board in final["boards"]}
            chosen = choose(registry, dims["observations"], board_weights)
        final.update(
            query=request["query"], synthetic=request.get("synthetic", False), registry=registry,
            dimensions=chosen["values"], dimension_conflicts=chosen["conflicts"],
            dimension_out_of_context=chosen["out_of_context"],
            pareto=pareto_charts(registry, chosen["values"], final["candidates"]),
            collection=collection, dependencies=weights.get("dependencies", {}),
            unselected_boards=[board for board in weights.get("boards", []) if not board.get("selected")],
            warnings=weights.get("warnings", []),
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            publication={
                "schema_version": SCHEMA_VERSION, "generation": attempt["generation"],
                "runtime": runtime_identity(), "input_sha256": inputs,
                "source_sha256": {name: digest for name, digest in inputs.items() if name in source_names},
                "weigh_generation": weigh_receipt["generation"],
            },
        )
        # Construct every format before replacing any public file.
        outputs = {"final.json": json_text(final), "leaderboard.md": to_markdown(final),
                   "leaderboard.csv": to_csv(final), "report.html": to_html(final)}
        publish(run, "score", attempt, inputs, outputs)
        counts = final["counts"]
        print("Scored %d of %d leaderboards; ranked %d candidates. "
              "Wrote final.json, leaderboard.md, leaderboard.csv, report.html."
              % (counts["scored"], counts["selected"], counts["candidates_ranked"]))
    return _run_stage(args, "score", operation, {})


def cmd_render(args: argparse.Namespace) -> int:
    run = Path(args.run).resolve()
    with run_lock(run):
        prior_entry = check_stage(run, "score", ignore_html=True)
        entry = dict(prior_entry, outputs=dict(prior_entry["outputs"]))
        page = to_html(object_file(run / "final.json"))
        state = read_state(run)
        state["stages"]["score"] = dict(entry, status="rendering")
        wrote_html = False
        try:
            write_json(run / STATE_NAME, state)
            archive_outputs(run, ("report.html",), "Before HTML rebuild", state)
            write_text(run / "report.html", page)
            wrote_html = True
            if input_digests(run, "score") != entry["inputs"] or runtime_identity() != entry["runtime"]:
                raise StaleRunError("Inputs/runtime changed during HTML rebuild.")
            entry["outputs"]["report.html"] = file_digest(run / "report.html")
            state["stages"]["score"] = entry
            write_json(run / STATE_NAME, state)
            if (run / "diagnostic.json").exists():
                archive_outputs(run, ("diagnostic.json",), "Resolved by HTML rebuild", state)
        except (OSError, RunInputError, StaleRunError) as exc:
            # Restore the old receipt, not a new successful render claim. Its hashes
            # still make missing/changed HTML stale while ignore_html permits retry.
            state["stages"]["score"] = prior_entry
            code = EXIT_IO if isinstance(exc, OSError) else EXIT_INPUT if isinstance(exc, RunInputError) else EXIT_NO_RESULT
            diagnostic = {"stage": "render", "reason": str(exc), "exit_code": code}
            try:
                write_json(run / STATE_NAME, state)
            except (OSError, RunInputError) as restore_error:
                diagnostic["receipt_restore_error"] = str(restore_error)
            if wrote_html:
                try:
                    archive_outputs(run, ("report.html",), "Incomplete HTML rebuild", state)
                except (OSError, RunInputError, StaleRunError) as cleanup_error:
                    diagnostic["cleanup_error"] = str(cleanup_error)
            try:
                write_json(run / "diagnostic.json", diagnostic)
            except (OSError, RunInputError) as diagnostic_error:
                print("Render failure diagnostic could not be saved: %s" % diagnostic_error, file=sys.stderr)
            raise  # Preserve the original error even when cleanup also fails.
        print(run / "report.html")
    return EXIT_OK

def cmd_verify(args: argparse.Namespace) -> int:
    run = Path(args.run).resolve()
    if not run.is_dir():
        raise RunInputError("Run folder does not exist: %s" % run)
    for name in ("request.json", "boards.json", "weights.json", "matches.json", "dimensions.json", "final.json"):
        if (run / name).exists():
            object_file(run / name)
    if (run / "request.json").exists():
        request_file(run)
    if (run / "boards.json").exists():
        boards_file(run)
    if (run / "matches.json").exists():
        matches_file(run)
    read_visits(run)
    result = verify_run(run)
    if args.json:
        print(json_text(result), end="")
    elif result["current"]:
        print("Saved weigh/score outputs are current. %s" % result["scope"])
    else:
        print("Saved run is stale or incomplete:", file=sys.stderr)
        for issue in result["issues"]:
            print("- " + issue, file=sys.stderr)
    return EXIT_OK if result["current"] else EXIT_NO_RESULT


def cmd_doctor(args: argparse.Namespace) -> int:
    print("ihav-leaderboards %s on Python %s" % (__version__, sys.version.split()[0]))
    web_chat = Path(args.project) / ".ihav_space" / "ihav-web-chat"
    print("ihav-web-chat runs in this project: %s" % ("found" if web_chat.is_dir() else "none yet"))
    print("This checks local folders only; it does not prove dependency installation or provider readiness.")
    warning = gitignore_warning(Path(args.project))
    if warning:
        print(warning)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = Parser(prog="ihav-leaderboards",
                    description="Merge public leaderboards into one quality-first leaderboard.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("new", help="create a run folder and print its path")
    p.add_argument("query", help="what to rank, for example 'OCR API'")
    p.add_argument("--project", default=".", help="project root")
    p.add_argument("--synthetic", action="store_true", help="label offline fixture runs")
    p.set_defaults(func=cmd_new)
    p = sub.add_parser("weigh", help="boards.json + visits/*.json -> source-bound weights.json")
    p.add_argument("run", help="run folder")
    p.add_argument("--top", type=int, default=TOP_N)
    p.set_defaults(func=cmd_weigh)
    p = sub.add_parser("score", help="current weights + extracted tables -> all four report formats")
    p.add_argument("run", help="run folder")
    p.set_defaults(func=cmd_score)
    p = sub.add_parser("render", help="current final.json -> report.html")
    p.add_argument("run", help="run folder")
    p.set_defaults(func=cmd_render)
    p = sub.add_parser("verify", help="read-only input/output receipt verification")
    p.add_argument("run", help="run folder")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_verify)
    p = sub.add_parser("doctor", help="check local Python and run folders")
    p.add_argument("--project", default=".")
    p.set_defaults(func=cmd_doctor)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = None
    try:
        args = build_parser().parse_args(argv)
        return args.func(args)
    except (StaleRunError, DependencyContractError, RunBusyError) as exc:
        if args is not None and args.command == "verify" and args.json:
            print(json_text({"current": False, "error": str(exc), "exit_code": EXIT_NO_RESULT}), end="")
        else:
            print("Saved run cannot be used: %s" % exc, file=sys.stderr)
        return EXIT_NO_RESULT
    except (RunInputError, KeyError, TypeError, ValueError, OverflowError) as exc:
        if args is not None and args.command == "verify" and args.json:
            print(json_text({"current": False, "error": str(exc), "exit_code": EXIT_INPUT}), end="")
        else:
            print("Input error: %s" % exc, file=sys.stderr)
        return EXIT_INPUT
    except OSError as exc:
        print("Local I/O failed: %s" % exc, file=sys.stderr)
        return EXIT_IO
