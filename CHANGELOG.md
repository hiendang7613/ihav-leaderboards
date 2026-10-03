# Changelog

## 0.1.0 - 2026-10-03

- Claude Code and Codex plugin with one shared core and two thin skills.
- `new`, `weigh`, `score` and `doctor` commands; Python 3.9+ standard library only, no network access.
- Visit weights from ihav-web-visit-counter: equal split per site, floor weight for rank-only sites, no-weight diagnostic.
- Min-max scoring, visit-weighted average and confidence; drops boards with fewer than 3 usable scores or equal scores; rank-only boards reported, not scored.
- Extra dimensions with comparable contexts, source precedence, typed conflicts and a Pareto frontier per numeric dimension.
- Markdown, CSV and JSON output under `.ihav_space/ihav-leaderboards/`.
