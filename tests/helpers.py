from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/ihav-leaderboards"
CORE = PLUGIN / "core/ihav-leaderboards"
SCRIPT = CORE / "scripts/leaderboards.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))


def visit(domain):
    return json.loads((FIXTURES / "visits" / ("%s.json" % domain)).read_text(encoding="utf-8"))


def estimate(domain, visits):
    return {"domain": domain, "kind": "estimate", "monthly_visits": visits, "period": None,
            "analyzed_at": "2026-10-03T00:00:00Z", "source": {"name": "test"}}


def rank_only(domain):
    return {"domain": domain, "kind": "rank_only", "monthly_visits": None, "period": None,
            "analyzed_at": None, "source": {"name": "Tranco"}}


def board(slug, rows, direction="higher_better", score_kind="score", **extra):
    value = {"slug": slug, "direction": direction, "score_kind": score_kind,
             "rows": [{"name": n, "quality": q, "verified": True} for n, q in rows]}
    value.update(extra)
    return value


def matches(names, boards):
    """Identity matching: each name is its own candidate on every board."""
    return {"candidates": [{"id": n, "name": n, "aliases": [{"board": b, "name": n} for b in boards]}
                           for n in names]}


def weights(masses):
    return {"boards": [{"slug": s, "mass": m, "selected": True} for s, m in masses.items()]}
