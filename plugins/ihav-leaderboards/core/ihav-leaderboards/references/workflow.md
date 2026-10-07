# ihav-leaderboards workflow

Shared by the Claude Code and Codex skills. `<cli>` means the bundled command:
`python3 <skill-directory>/scripts/leaderboards.py` (use `py -3` on Windows).

## Hard rules

1. **Never fill a gap from memory.** Every URL, visit count, score and dimension value comes from a saved source. A gap stays `null` with a reason.
2. **No bypass.** On HTTP 401, 403, 429, a captcha or a bot wall, stop using that source. Do not retry it, and do not switch browser, proxy or route to get past it. Only other permitted sources may be tried.
3. **Visit lookups:** a network error may be retried once. A blocked or rate-limited lookup (exit code 4) is never retried.
4. **Never invent weights.** Exit 2 can mean a busy run: wait for the named writer, then retry the local command without editing inputs or resending requests. Otherwise report the `weigh`/`score` diagnostic or `render`/`verify` stale/incomplete reason. Never fall back to equal weights.
5. **Agent-only matching.** Do not ask the user to match names. Record every decision in `matches.json`.
6. All run files go under `.ihav_space/ihav-leaderboards/runs/<run-id>/` in the user's project.

## Stages

### 0. Check dependencies

ihav-leaderboards needs two other plugins: **ihav-web-chat** (before stage 2) and **ihav-web-visit-counter** (before stage 3). Check the host's installed plugins. Do not assume a binary on `PATH`, and do not pick a cache folder by date.

Find each plugin root this way:

- **Claude Code:** `claude plugin list --json`. Use the entry whose `id` starts with the plugin name, has `"enabled": true` and has an `installPath`. That path is `<plugin-root>`.
- **Codex:** `codex plugin list --json`. Its `installed` list shows `installed`, `enabled` and `version`, but no install path for a catalog install. Use the path of the plugin's skill as the host shows it. If the host shows no path, stop and ask the user for it.
- If two enabled entries match, or none does, stop and show the matches to the user. Do not choose one yourself.

Then check the contract of each plugin before you use it:

- **ihav-web-visit-counter:** each new `--json` result or error object carries `contract_version` 2. If a new lookup prints another number, stop and report it. Older saved files may have no `contract_version`; never add the field to a saved file.
- **ihav-web-chat:** `python3 <plugin-root>/bin/ihav-web-chat doctor --json` lists the commands `run`, `run lookup`, `delivery wait` and `delivery read`. Read the plugin version from `<plugin-root>/.claude-plugin/plugin.json`; `doctor` prints the runtime version, which is a different number.

If ihav-web-visit-counter is missing, stop before stage 3. Save what the run already has, and print the install commands from the ihav catalog:

```bash
claude plugin marketplace add hiendang7613/ihav
claude plugin install ihav-web-visit-counter@ihav
```

```bash
codex plugin marketplace add hiendang7613/ihav
codex plugin add ihav-web-visit-counter@ihav
```

ihav-web-chat is not in the ihav catalog yet, so there is no install command to print. If it is missing, stop before stage 2 and say: "Discovery needs ihav-web-chat, which is not released in the ihav catalog yet: https://github.com/hiendang7613/ihav-web-chat". Do not print an `ihav-web-chat@ihav` command.

In Claude Code, installing ihav-leaderboards from the ihav catalog also installs ihav-web-visit-counter. Codex installs no dependencies. Installing a plugin needs the user's permission in the host; this check does not grant it. After an install, check the list again and resume the run from its saved files. Never resend a chatbot request that already has a saved answer.

### 1. New run

```bash
<cli> new "OCR API"
```

Prints the run folder. Use it as `RUN` below.

`request.json` uses schema 2. Record the actual dependency identities in its `dependencies` object before weighing: visit-counter manifest `version` and `manifest_sha256`; web-chat manifest `version` plus `runtime.json` `bundle_version`, `runtime_version` and `source_tree_sha256`. Never infer an installed version from a saved response. Do not put personal install paths into shareable metadata. Saved schema-1 runs remain readable; missing package versions and visit contracts are reported as unrecorded or `legacy_unversioned`, never invented. If a dependency root is still unknown, leave its identity fields unrecorded and record the locator problem in run notes; never guess a manifest or cache path. Continue independent offline work only until the supported locator is available. Use `new ... --synthetic` only for fabricated offline fixtures.

### 2. Discover (S1)

Write one deep-research prompt that asks for up to 32 public leaderboards or benchmarks for the query. Ask for a fenced JSON list. Each item has `url`, `owner`, `measures`, `main_metric`, `direction` (`higher_better` or `lower_better`), `last_updated`, and `dimensions` (other columns such as price, latency or throughput).

If ihav-web-chat is not installed, follow stage 0.

Send the prompt with **ihav-web-chat**. `<web-chat>` means `python3 <plugin-root>/bin/ihav-web-chat`. Always pass `--project` with the user's project, so its run folders go to `.ihav_space/ihav-web-chat/runs/` there. Steps:

1. **Providers.** Run `<web-chat> providers --json`. The default providers are ChatGPT and Gemini. The user may name more providers, or `all`. Ask only for providers that the list shows. Report each default that is missing, for example "Gemini is not available in the installed ihav-web-chat".
2. **Prompt file.** Save the prompt as `RUN/discovery/prompt.md`. It must not be longer than the provider's `limits.max_prompt_chars`.
3. **Reuse.** The request key is `<run-id>-discovery`, where `<run-id>` is the name of the `RUN` folder. Run `<web-chat> run lookup --request-key <key> --project <project> --json`. If it lists a run id, use that run and go to step 6. Never queue the same request again.
4. **Preview.** Run `<web-chat> run --providers <list> --prompt-file RUN/discovery/prompt.md --project <project> --request-key <key> --dry-run --json`. It writes and sends nothing.
5. **Approval, then queue.** Show the user the exact prompt and the provider list. Ask for approval to send this prompt to these providers. Only after approval, run the same command without `--dry-run`. Save the printed `run_id` in `RUN/discovery/web-chat.json` at once. A queued run is not a sent prompt.
6. **Wait and read.** Run `<web-chat> delivery wait <run_id> --project <project> --timeout <seconds> --json`. Exit code 4 means the wait timed out, not that a provider failed; check again later. Exit code 0 does not mean success: read each provider's `status`. Then run `<web-chat> delivery read <run_id> --project <project> --json --include-text` to get the answer text of `completed` providers.

A provider whose status is `failed`, `timeout`, `login_required`, `human_verification_required`, `not_sent`, `sent_unknown` or `cancelled` gave no answer. Report its status and reason, and continue with the others (`partial`). Never resend, also not after `sent_unknown` or a timeout. If no provider answered, stop and report it.

ihav-web-chat 0.0.5 can queue a run, but it has no command that sends it ("a worker sends and observes, and it has no CLI command yet"). The run moves only if some other process runs a sender on the same queue. If `delivery wait` still shows `queued` at its timeout, report that the run is queued and not sent. Do not try to start a worker or a browser yourself.

Save each answer as `RUN/discovery/<provider>.json` (the parsed list) and keep the ihav-web-chat run id in it.

### 3. Collect (S2)

Merge the lists. Normalize URLs (scheme, `www`, trailing slash, tracking parameters). Check each URL once with an ordinary GET and classify it in this order: `blocked` (401/403, captcha, bot wall), `rate_limited` (429), `transient` (5xx or timeout, one later retry), `dead` (404/410, other 4xx, DNS), else `live`. Follow redirects, then dedupe again by final URL.

Run **ihav-web-visit-counter** once per host of each `live` board's final URL after redirects, with `--json`: `python3 <plugin-root>/core/ihav-web-visit-counter/scripts/visits.py <url> --json --cache-dir .ihav_space/ihav-web-visit-counter`. Its `domain` field is the host (no path, no leading `www`, subdomains kept). Visits are per host, never per page. Look up each host once per run, at most one lookup per second, and pass `--cache-dir .ihav_space/ihav-web-visit-counter` so the whole run shares one 24-hour cache. The visit sources allow only reasonable, low-volume use. Never re-run a lookup for a host that ended with exit code 4 (blocked). A lookup that exits 2, 4 or 5 prints an error object instead of a result; save it too. `weigh` treats it as no data (floor weight) and keeps its `error.notes` out of the visit numbers. Save each result as `RUN/visits/<domain>.json`, unchanged. An error object has no `domain` field, so the file name is the only record of its host.

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

It also commits a `run_state.json` receipt containing input hashes, configuration, schema, runtime identity and the output hash. A new weigh attempt invalidates the score stage. Existing weights and reports are copied and hash-checked in a timestamped `.history/` folder before removal. The manifest records verified copies and removal progress. Storage failures can leave old files at the run root with a failed receipt; inspect `diagnostic.json` and the archive manifest before recovery. Unsupported visit contracts exit 2; malformed input exits 64. Domain-less visit errors use the saved filename as their host and retain their error code. Error objects cannot also contain result fields. Legacy versions 1 and missing versions are labelled explicitly, without changing the child JSON.

Every live board needs an HTTP(S) `final_url` (or `url`) whose host matches `domain`. Match the visit counter's normalization: lowercase, remove trailing dots and one leading `www.`, keep subdomains, and encode international host names with IDNA. A redirect to another host requires updating the collected domain and using that host's saved visit result. Do not borrow traffic from the original host.

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

The CLI binds extraction to the collected `final_url`, checks the saved snapshot SHA-256 and requires a nonempty `cell` on each verified row. Missing or changed evidence stays unverified. A hash proves saved bytes, not that a person accepted the extraction. Keep `complete: true` only after reading the full accessible table. Partial tables cannot supply the board's normalization bounds.

### 6. Match (S5)

Write `RUN/matches.json`. A candidate's identity is vendor + product type + model/version + configuration. Normalized names only propose a match. Merge two names only with source evidence that they measure the same thing. Versions stay separate. Two vendors with the same product name stay separate.

If two verified rows on one board map to the same candidate and their values differ, choose the best-evidenced row yourself and set `"preferred": true` on exactly one row. Equal values need no preferred marker; the CLI keeps the one marked preferred or the first row. Never mark two rows preferred. Conflicting values without exactly one preferred row, or any group with multiple preferred rows, make the board `unverified` with `duplicate_conflicts`; the board does not score. Record your evidence and choice in `matches.json`. Other equal/selected rows are reported as duplicates. Do not ask the user to choose.

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
                   "url": "https://...", "date": "2026-10-03",
                   "snapshot": "snapshots/vendor-pricing.html", "snapshot_sha256": "...",
                   "cell": "pricing table, base OCR row, USD per 1,000 pages column"}]}
```

Only observations in the registry's declared `context` compete. `source_type` is `leaderboard` (set `board`) or `official`. Every usable comparable observation needs a saved snapshot, matching SHA-256 and nonempty `cell` or `locator`. Every leaderboard observation binds to its validated extraction's snapshot through `board` and a cell locator; an explicitly supplied snapshot/hash must match that board. Official observations need their own saved evidence. Missing or changed dimension evidence exits 64 before any comparison is published; null values remain missing. Unlike dropping an unverified quality board and renormalizing its weights, silently dropping a dimension can change which comparisons are available. Correct its declared evidence or explicitly record a missing value before scoring. The report keeps the chosen observation's snapshot, digest and locator.

### 8. Score (S6)

```bash
<cli> score RUN
```

Writes `RUN/final.json`, `RUN/leaderboard.md`, `RUN/leaderboard.csv` and `RUN/report.html` (interactive charts). `<cli> render RUN` rebuilds only the HTML report from `final.json`.

`score` first requires a current weigh receipt. It builds all four formats, replaces them, then commits the score receipt last. Files are current only when the receipt and hashes validate; individual file existence is insufficient. Changed inputs, code, schema or recorded dependency identities require local `weigh`/`score` again. A failed score attempt archives old outputs and keeps every selected board's failure reason in `diagnostic.json` when no board can score. Never rediscover or resend a child request to repair local arithmetic or report state.

Run the read-only final check:

```bash
<cli> verify RUN --json
```

Exit 0 means saved inputs, declared evidence links and all four output hashes are current. It does not prove provider delivery, clean-host installation or human acceptance. Exit 2 means a busy run or stale/incomplete/no-result state; wait for a busy writer without editing inputs, otherwise inspect its issues and rerun only the required local stages. Exit 64 means malformed input; correct the saved file before retrying. Local I/O failure exits 1. After `weigh` alone, `verify` returns 2 because scoring is incomplete. `render` requires current score inputs and the other three outputs; it can repair a missing or changed HTML file. A failed HTML rebuild records its original error and restores the prior score receipt when storage permits, so `render` can retry without recomputing scores. Missing/changed HTML still makes `verify` return 2. History/archive directories must stay inside the run and cannot be symlinks.

CLI writers use one local run lock. Another writer exits 2 without changing the run; wait for it to finish before retrying. OS process exit releases the lock. The lock does not prevent an editor changing input files; input hashes are rechecked before publication.

CSV appends a `synthetic` boolean column. Reports show a synthetic banner for fabricated fixtures, missing dependency/version warnings, traffic periods and floor/split policy, matching confidence/evidence, and chart omissions. Score confidence remains source-weight coverage.

## Report to the user

Show the top of `leaderboard.md` and give the path of `report.html`. Say how many boards were selected and scored. Name each dropped board with its reason. Explain once that `confidence` is the share of scored source weight behind a score, not statistical certainty. Say that weights are allocated domain popularity, not page visits.

Report the `verify` result and its scope. Keep live/provider, browser and human checks separate. Archived outputs are recovery data; they are not current results.
