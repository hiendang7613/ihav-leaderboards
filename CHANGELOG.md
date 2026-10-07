# Changelog

## Unreleased

- Visit estimates accept trillion (`T`) display labels while preserving the saved counter's raw integer or null. Single-domain and mixed-domain regressions cover the weighting policy.
- Reject unknown extraction score kinds, require source snapshots for rank-only boards, and refuse a receipt that changes during read-only verification. The synthetic example carries current runtime receipts; long tooltip text wraps within its panel.
- Deterministic CLI candidate 0.3.0: validated stage identities and SHA-256 receipts, read-only `verify`, stale-input refusal, and recoverable output archives. Archives verify backups before removal, journal partial failures and reject history symlinks. Failed HTML rebuilds retain the prior receipt for retry. This does not establish live/provider or clean-host acceptance.
- Scores require literal verification and saved source/cell references. Conflicting duplicate rows require one explicit preferred row; no duplicate group can contain multiple preferred rows. Numeric conversion and normalization remain finite at float extremes.
- Reports retain traffic and identity evidence, typed dimension choices and conflicts. Traffic binds to the collected URL host; error and result payloads cannot mix. Comparable dimensions need saved source hashes and cell locators; leaderboard dimensions bind to the referenced board snapshot. Numeric dimension cards and explicit chart omissions are visible. CSV text is formula-safe and carries a synthetic-data column; Markdown escapes dynamic cells.
- Skills: ihav-web-chat is not in the ihav catalog yet, so the skill no longer prints an `ihav-web-chat@ihav` install command.
- Discovery follows the ihav-web-chat 0.0.5 contract: `--dry-run` preview, approval of the exact prompt, one request key per run, `delivery wait/read`, no resend.
- Stage 0 finds each dependency through `claude plugin list --json` or `codex plugin list --json` and checks its contract.

## 0.2.2 - 2026-10-04

- Claude Code installs ihav-web-visit-counter automatically as a dependency (from the ihav catalog). Codex has no dependency install; the skill still checks and prints the install command.
- Docs: ihav-web-chat's CLI option is `--providers`.

## 0.2.1 - 2026-10-03

- Weights accept visit-counter estimates that carry only a rounded label such as `631.0M` (`monthly_visits_text`).
- Docs: visit-counter `domain` is the host, not the registrable domain.
- Visit lookups: one per host per run, at most one per second, shared 24-hour cache, no re-run after a block.
- Skill checks that ihav-web-chat and ihav-web-visit-counter are installed before the stages that need them, and prints install commands from the ihav catalog.

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
