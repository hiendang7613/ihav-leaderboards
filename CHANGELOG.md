# Changelog

## 0.2.0 - 2026-10-03

- `report.html`: one static, shareable page in the style of artificialanalysis.ai, written by `score` (or `render`).
- Charts: quality ranking with a confidence meter, quality vs each dimension with a Pareto frontier (dimension selector, dot size = confidence, log scale when values span 50x), coverage grid, leaderboard weights, sortable table.
- Light and dark themes, keyboard-focusable tooltips, data inserted with `textContent` only.
- `examples/synthetic-ocr/`: a complete, clearly synthetic run with every file.

## 0.1.0 - 2026-10-03

- Claude Code and Codex plugin with one shared core and two thin skills.
- `new`, `weigh`, `score` and `doctor` commands; Python 3.9+ standard library only, no network access.
- Visit weights from ihav-web-visit-counter: equal split per site, floor weight for rank-only sites, no-weight diagnostic.
- Min-max scoring, visit-weighted average and confidence; drops boards with fewer than 3 usable scores or equal scores; rank-only boards reported, not scored.
- Extra dimensions with comparable contexts, source precedence, typed conflicts and a Pareto frontier per numeric dimension.
- Markdown, CSV and JSON output under `.ihav_space/ihav-leaderboards/`.
