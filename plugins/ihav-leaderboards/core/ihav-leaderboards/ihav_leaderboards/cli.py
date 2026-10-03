"""Command line for the deterministic stages: new, weigh, score, doctor.

Discovery (S1), collection (S2) and extraction (S4) are run by the agent, which writes
the run-folder files these commands read. This module makes no network call.

Exit codes: 0 success, 2 no weight or no scored leaderboard (a diagnostic is written),
64 bad input.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from . import __version__
from .dimensions import choose, pareto_charts
from .render import to_html
from .runs import RunInputError, create_run, gitignore_warning, read_folder, read_json, read_visits, write_json
from .scoring import NoScoreError, merge
from .tables import to_csv, to_markdown
from .weights import TOP_N, NoWeightError, allocate

EXIT_OK, EXIT_NO_RESULT, EXIT_INPUT = 0, 2, 64


def cmd_new(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    run = create_run(project, args.query)
    print(run)
    warning = gitignore_warning(project)
    if warning:
        print(warning, file=sys.stderr)
    return EXIT_OK


def cmd_weigh(args: argparse.Namespace) -> int:
    run = Path(args.run)
    boards = read_json(run / "boards.json").get("boards", [])
    try:
        weights = allocate(boards, read_visits(run), top_n=args.top)
    except NoWeightError as exc:
        write_json(run / "diagnostic.json", {"stage": "weigh", "reason": str(exc)})
        print(str(exc), file=sys.stderr)
        return EXIT_NO_RESULT
    write_json(run / "weights.json", weights)
    selected = sum(1 for e in weights["boards"] if e["selected"])
    print("Selected %d of %d live leaderboards. Floor weight used for %d domain(s)."
          % (selected, len(weights["boards"]), len(weights["floor_domains"])))
    return EXIT_OK


def cmd_score(args: argparse.Namespace) -> int:
    run = Path(args.run)
    weights = read_json(run / "weights.json")
    matches = read_json(run / "matches.json")
    boards = read_folder(run / "leaderboards")
    try:
        final = merge(boards, weights, matches)
    except NoScoreError as exc:
        write_json(run / "diagnostic.json", {"stage": "score", "reason": str(exc)})
        print(str(exc), file=sys.stderr)
        return EXIT_NO_RESULT

    dims_path = run / "dimensions.json"
    registry, chosen = [], {"values": {}, "conflicts": [], "out_of_context": 0}
    if dims_path.exists():
        dims = read_json(dims_path)
        registry = dims.get("registry", [])
        board_weights = {b["slug"]: b["weight"] for b in final["boards"]}
        chosen = choose(registry, dims.get("observations", []), board_weights)

    request = run / "request.json"
    final["query"] = read_json(request).get("query") if request.exists() else None
    final["registry"] = registry
    final["dimensions"] = chosen["values"]
    final["dimension_conflicts"] = chosen["conflicts"]
    final["dimension_out_of_context"] = chosen["out_of_context"]
    final["pareto"] = pareto_charts(registry, chosen["values"], final["candidates"])

    final["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    write_json(run / "final.json", final)
    (run / "leaderboard.md").write_text(to_markdown(final), encoding="utf-8")
    (run / "leaderboard.csv").write_text(to_csv(final), encoding="utf-8")
    (run / "report.html").write_text(to_html(final), encoding="utf-8")
    counts = final["counts"]
    print("Scored %d of %d leaderboards; ranked %d candidates. Wrote final.json, leaderboard.md, "
          "leaderboard.csv, report.html." % (counts["scored"], counts["selected"], counts["candidates_ranked"]))
    return EXIT_OK


def cmd_render(args: argparse.Namespace) -> int:
    run = Path(args.run)
    final = read_json(run / "final.json")
    (run / "report.html").write_text(to_html(final), encoding="utf-8")
    print(run / "report.html")
    return EXIT_OK


def cmd_doctor(args: argparse.Namespace) -> int:
    print("ihav-leaderboards %s on Python %s" % (__version__, sys.version.split()[0]))
    web_chat = Path(args.project) / ".ihav_space" / "ihav-web-chat"
    print("ihav-web-chat runs in this project: %s" % ("found" if web_chat.is_dir() else "none yet"))
    warning = gitignore_warning(Path(args.project))
    if warning:
        print(warning)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ihav-leaderboards",
                                     description="Merge public leaderboards into one quality-first leaderboard.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("new", help="create a run folder and print its path")
    p.add_argument("query", help="what to rank, for example 'OCR API'")
    p.add_argument("--project", default=".", help="project root (default: current directory)")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("weigh", help="boards.json + visits/*.json -> weights.json")
    p.add_argument("run", help="run folder")
    p.add_argument("--top", type=int, default=TOP_N, help="leaderboards to keep (default %d)" % TOP_N)
    p.set_defaults(func=cmd_weigh)

    p = sub.add_parser("score", help="leaderboards/, matches.json, weights.json -> final.json, md, csv")
    p.add_argument("run", help="run folder")
    p.set_defaults(func=cmd_score)

    p = sub.add_parser("render", help="final.json -> report.html")
    p.add_argument("run", help="run folder")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("doctor", help="check the local setup")
    p.add_argument("--project", default=".")
    p.set_defaults(func=cmd_doctor)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (RunInputError, KeyError, TypeError) as exc:
        print("Input error: %s" % exc, file=sys.stderr)
        return EXIT_INPUT
