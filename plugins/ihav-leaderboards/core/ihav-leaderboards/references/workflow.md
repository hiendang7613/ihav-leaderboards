# ihav-leaderboards workflow

Shared by the Claude Code and Codex skills. `<cli>` means the bundled command:
`python3 <skill-directory>/scripts/leaderboards.py` (use `py -3` on Windows).

## Hard rules

1. **Never fill a gap from memory.** Every URL, visit count, score and dimension value comes from a saved source. A gap stays `null` with a reason.
2. **No bypass.** On HTTP 401, 403, 429, a captcha or a bot wall, stop using that source. Do not retry it, and do not switch browser, proxy or route to get past it. Only other permitted sources may be tried.
3. **Visit lookups:** a network error may be retried once. A blocked or rate-limited lookup (exit code 4) is never retried.
4. **Never invent weights.** If `weigh` or `score` exits with code 2, report the diagnostic. Do not fall back to equal weights.
5. **Agent-only matching.** Do not ask the user to match names. Record every decision in `matches.json`.
6. All run files go under `.ihav_space/ihav-leaderboards/runs/<run-id>/` in the user's project.

## Stages

### 0. Check dependencies

ihav-leaderboards needs two other plugins: **ihav-web-chat** (before stage 2) and **ihav-web-visit-counter** (before stage 3). Check the host's installed plugins, for example `claude plugin list` or `codex plugin list`. Do not assume a binary on `PATH`, and do not pick a cache folder by date.

If one is missing, stop before the stage that needs it. Save what the run already has, and print the install commands from the ihav catalog:

```bash
claude plugin marketplace add hiendang7613/ihav
claude plugin install <plugin>@ihav
```

```bash
codex plugin marketplace add hiendang7613/ihav
codex plugin add <plugin>@ihav
```

Installing a plugin needs the user's permission in the host; this check does not grant it. After an install, check the list again and resume the run from its saved files. Never resend a chatbot request that already has a saved answer.

### 1. New run

```bash
<cli> new "OCR API"
```

Prints the run folder. Use it as `RUN` below.

### 2. Discover (S1)

Write one deep-research prompt that asks for up to 32 public leaderboards or benchmarks for the query. Ask for a fenced JSON list. Each item has `url`, `owner`, `measures`, `main_metric`, `direction` (`higher_better` or `lower_better`), `last_updated`, and `dimensions` (other columns such as price, latency or throughput).

Send it with the **ihav-web-chat** skill. The default providers are ChatGPT and Gemini. The user may name more providers, or `all`. Wait for the answers. If one provider fails, continue with the others. If none answers, stop and report it.

If ihav-web-chat is not installed, follow stage 0.

Save each answer as `RUN/discovery/<provider>.json` (the parsed list) and keep the ihav-web-chat run id in it.

### 3. Collect (S2)

Merge the lists. Normalize URLs (scheme, `www`, trailing slash, tracking parameters). Check each URL once with an ordinary GET and classify it in this order: `blocked` (401/403, captcha, bot wall), `rate_limited` (429), `transient` (5xx or timeout, one later retry), `dead` (404/410, other 4xx, DNS), else `live`. Follow redirects, then dedupe again by final URL.

Run **ihav-web-visit-counter** on each URL with `--json`. Its `domain` field is the host (no path, no leading `www`, subdomains kept). Visits are per host, never per page. Look up each host once per run, at most one lookup per second, and pass `--cache-dir .ihav_space/ihav-web-visit-counter` so the whole run shares one 24-hour cache. The visit sources allow only reasonable, low-volume use. Never re-run a lookup for a host that ended with exit code 4 (blocked). A lookup that exits 2, 4 or 5 prints an error object instead of a result; save it too. `weigh` treats it as no data (floor weight) and keeps its `error.notes` out of the visit numbers. Save each result as `RUN/visits/<domain>.json`, unchanged.

Write `RUN/boards.json`:

```json
{"boards": [{"slug": "ocr-arena", "url": "...", "final_url": "...", "domain": "example.org",
             "status": "live", "mentioned_by": ["chatgpt", "gemini"]}]}
```

### 4. Weigh (S3)

```bash
<cli> weigh RUN
```

Writes `RUN/weights.json`: domain visits split equally across that domain's boards, a floor weight for domains with no estimate, and the top 32 selected.

### 5. Extract (S4)

For each selected board, in this order: (a) a direct data endpoint, CSV, JSON or static HTML table; (b) a real browser render of an accessible page, following pagination; (c) ask a chatbot through ihav-web-chat to read the page. Save the source snapshot and its SHA-256.

Write `RUN/leaderboards/<slug>.json`:

```json
{"slug": "ocr-arena", "final_url": "...", "fetched_at": "2026-10-03T10:00:00Z",
 "method": "direct", "snapshot": "snapshots/ocr-arena.html", "snapshot_sha256": "...",
 "complete": true, "quality_column": "Accuracy", "direction": "higher_better",
 "score_kind": "score",
 "rows": [{"name": "Vendor OCR v3", "quality": 91.2, "verified": true, "cell": "table#lb tr:nth-child(2) td:nth-child(3)"}]}
```

- `score_kind` is `rank_only` when the board gives only an order. Rank-only boards are reported but not scored.
- Use the board's main ranking column. Set `direction` to `lower_better` for error rates such as CER or WER.
- A chatbot-read row is `verified: true` only after you match it against the accessible source content. Otherwise set `verified: false`.
- If extraction fails, write `{"slug": "...", "status": "extract_failed", "reason": "..."}`.

### 6. Match (S5)

Write `RUN/matches.json`. A candidate's identity is vendor + product type + model/version + configuration. Normalized names only propose a match. Merge two names only with source evidence that they measure the same thing. Versions stay separate. Two vendors with the same product name stay separate.

```json
{"candidates": [{"id": "vendor-ocr-v3", "name": "Vendor OCR v3", "vendor": "Vendor",
                 "aliases": [{"board": "ocr-arena", "name": "Vendor OCR v3"}],
                 "evidence": "...", "confidence": "high"}]}
```

### 7. Dimensions (S6b)

Write `RUN/dimensions.json` with a registry and observations. The registry is seeded from discovery and grows when boards or official pages show new dimensions.

```json
{"registry_version": 1,
 "registry": [{"key": "price", "unit": "USD per 1,000 pages", "type": "number",
               "direction": "lower_better", "context": "base OCR, pay-as-you-go"}],
 "observations": [{"id": "o1", "candidate": "vendor-ocr-v3", "key": "price", "value": 1.5,
                   "context": "base OCR, pay-as-you-go", "source_type": "official",
                   "url": "https://...", "date": "2026-10-03"}]}
```

Only observations in the registry's declared `context` compete. `source_type` is `leaderboard` (set `board`) or `official`.

### 8. Score (S6)

```bash
<cli> score RUN
```

Writes `RUN/final.json`, `RUN/leaderboard.md`, `RUN/leaderboard.csv` and `RUN/report.html` (interactive charts). `<cli> render RUN` rebuilds only the HTML report from `final.json`.

## Report to the user

Show the top of `leaderboard.md` and give the path of `report.html`. Say how many boards were selected and scored. Name each dropped board with its reason. Explain once that `confidence` is the share of scored source weight behind a score, not statistical certainty. Say that weights are allocated domain popularity, not page visits.
