# ihav-leaderboards: design spec v1 (draft)

Status: v1, 2026-10-03. v0 plus a peer design review (findings F1-F7, applied here). Release 0.1.0 implemented S3, S6, S6a and S6b in the `weigh` and `score` commands; S1, S2, S4 and S5 are agent-driven steps in the skill workflow; release 0.2.0 adds the HTML report (section 3).
Owner decisions of 2026-10-03 are listed in section 1.
Evidence labels: **owner** = owner decision; **verified** = read in a local file on 2026-10-03; **proposed** = design choice made here, open to review; **unverified** = needs a live check.

## 1. Goal and owner decisions

Goal (owner): the user names a domain ("I need an OCR API"). The plugin finds the most-visited public leaderboards for that domain, extracts their tables, and merges them into one quality-first leaderboard with charts in the style of artificialanalysis.ai, including a Pareto frontier. Ships as a Claude Code and Codex plugin, GitHub-trend quality.

| ID | Owner decision |
|---|---|
| Q1 | Missing score: average only over leaderboards that contain the candidate (renormalized). Also show a confidence score = weight present / total weight, in the table and in the charts. |
| Q2 | No hard coverage threshold; show the confidence score instead. |
| Q3 | Use each leaderboard's main ranking column; invert lower-is-better metrics; record the choice. |
| Q4 | Weights come from `ihav-web-visit-counter`, built by another Codex-Claude team. Design against its contract. |
| Q5 | Table extraction order: direct HTML/JSON/CSV, then browser, then chatbot via `ihav-web-chat`. |
| Q6 | The agent does all name matching. The user does nothing. |
| Q7 | One public repo per plugin, Claude + Codex manifests, plus an `ihav` marketplace repo. |
| Q8 | Output `leaderboard.md`, `leaderboard.csv` and one shareable HTML page; charts styled like artificialanalysis.ai; Pareto line is a headline feature. |
| R1 | Check every leaderboard URL is live before ranking. |
| R2 | Drop a leaderboard from scoring when it has too few candidates or `max == min`. "Too few" is defined in S6a (proposed). |

Non-goals for v0: paid data sources, API keys, bypassing logins or bot walls, live re-benchmarking of candidates, a hosted service.

## 2. Pipeline

```
domain prompt
  -> S1 discover   ask chatbots (ihav-web-chat) for candidate leaderboards
  -> S2 collect    union + dedupe URLs; liveness check (R1)
  -> S3 weigh      visits per leaderboard (ihav-web-visit-counter); take top 32 by weight
  -> S4 extract    table per leaderboard (Q5 order); provenance record
  -> S5 match      candidate names across leaderboards (agent-only, Q6)
  -> S6 score      min-max per leaderboard; weighted average; confidence
  -> S7 render     md, csv, json, html with charts
```

Every stage writes its output to `./.ihav_space/ihav-leaderboards/runs/<run-id>/` in the calling project (ihav family convention: every ihav plugin keeps its run-time folders and files under `.ihav_space/<plugin_name>/`). Child calls keep their own space: ihav-web-chat writes to `.ihav_space/ihav-web-chat/`, and this plugin stores only the child run IDs and copies it needs. The plugin warns, and does not edit, when `.ihav_space/` is missing from the project's `.gitignore`. Any stage can be resumed from its saved input. No stage fills a gap from model memory; a gap stays `null` with a reason.

### S1 discover (proposed)

- The plugin writes one deep-research prompt per run. It asks each chatbot for up to 32 public leaderboards or benchmarks for the domain, each with URL, owner, what it measures, main metric and direction, and last update date. Answer format: a fenced JSON list, so parsing is deterministic.
- Default providers: ChatGPT and Gemini (owner). Option `--providers a,b,c` or `--providers all` passes through to `ihav-web-chat run --providers`.
- `ihav-web-chat run` returns at once; answers arrive by callback (per the ihav-web-chat design contract, section 4, locally inspected; not demonstrated at runtime). S1 waits through `delivery wait/read`. A provider that ends `failed`, `timeout` or `login_required` is reported; the run continues with the others (`partial`). Zero answers stops the run with a clear message.
- Dependency (unverified): the owner goal asks for automatic install of ihav-web-chat. No verified plugin-to-plugin install mechanism exists in either host yet, so this goal is **open**, not fulfilled (review O5). Until it is resolved, S1 locates ihav-web-chat through an explicit host/plugin locator plus a version and contract check (not an assumed binary on `PATH`). If absent or incompatible, it prints the exact install command and stops.
- Bound (verified): ihav-web-chat v0 is macOS-only; its first milestone is ChatGPT, Gemini and Perplexity. `--providers all` means "all providers the installed ihav-web-chat supports".

### S2 collect (proposed)

- Normalize URLs (scheme, `www`, trailing slash, tracking params). Merge entries that point to the same page. Keep the list of chatbots that named each entry (`mentioned_by`).
- Liveness check (R1): one ordinary GET per URL, no bypass. Classes are disjoint and checked in this order (review F7): `blocked` (401/403, captcha, bot wall), `rate_limited` (429), `transient` (5xx, timeout; one later retry), `dead` (404/410, other 4xx, DNS), else `live`. Redirects are followed; the final URL is kept.
- Dedupe a second time by **final canonical URL** after redirects, so one board takes one slot.
- Eligibility: only `live` boards enter S3. `blocked`, `rate_limited`, `transient` and `dead` boards are report-only with their reason. Rendering an accessible JS page in a browser is allowed; escalating to get past a challenge is not.

### S3 weigh (proposed against the visit-counter contract)

The visit counter (verified against its shipped `models.py` and two live `--json` outputs on 2026-10-03) returns per **host** (scheme, path and a leading `www` removed; subdomains kept; never per page): `kind` in `estimate | rank_only`. `estimate` carries `monthly_visits`, or `null` plus a rounded label `monthly_visits_text` such as `631.0M`, which is parsed; `rank_only` carries `null`. Other fields: `period` (may be `null`), `analyzed_at`, `range`, `confidence`, `rank`, `source`, `history`, `countries`.
Two gaps follow, each with a proposed default:

1. **Domain collision (owner O1).** Many leaderboards are pages on one domain (Hugging Face Spaces, GitHub, Papers with Code). Domain visits do not measure one page. Rule: split a domain's monthly visits **equally** across the live leaderboards of that domain. Report `weight_basis: domain_split(n)`. The final ranking is therefore weighted by **allocated domain popularity**, not page visits; the report says so. The split depends on how many pages discovery found; this is a known limit of the proxy.
2. **No visit number (owner O2).** For `rank_only` or a typed no-data result (exit 2), use a **floor**: the smallest finite positive visit count in the set, `weight_basis: floor`. The floor is a policy weight, stored apart from `monthly_visits`, which stays `null`. It is never shown as visits or as an upstream `estimate`. A domain gets one floor before its split, not one per page. A network error (exit 5) may be retried once. Blocked or rate-limited (exit 4) is **never retried** against that provider, matching the visit-counter no-bypass rule; only other permitted sources may be tried. If both end without a count, the board is treated like no-data, with the reason kept.
3. **No weight at all (review F1).** If the set has no finite positive visit count, there is no floor and no weight. The run saves discovery and reasons, emits no final score and no Pareto frontier, and states that visit-weighted aggregation is unavailable. It does not fall back to equal weights silently.

Inputs are validated as finite and nonnegative. Stored per board: raw domain visits, `kind`, `period`, `range`, `source`, split count, allocated mass and `weight_basis`. Periods that differ are reported, not hidden.
Selection: top 32 by allocated mass. Boards that later fail extraction or S6a are **not replaced**; the report states selected, extracted and scored counts. `w_L` is renormalized over the scored set: `w_L = mass_L / Σ mass` over scored boards.

### S4 extract (proposed)

Extraction order per leaderboard (owner Q5): (a) direct fetch of a data endpoint, CSV, JSON or static HTML table; (b) real browser render, read the DOM table, follow pagination; (c) ask a chatbot through ihav-web-chat to read the page, labelled `method: chatbot` and lower trust. No bypass at any step.

Per-leaderboard provenance record (`leaderboards/<slug>.json`):

| Field | Meaning |
|---|---|
| `url`, `final_url`, `fetched_at` | Source and time |
| `method` | `direct`, `browser` or `chatbot` |
| `snapshot` | Saved source content (or minimal permitted cell evidence) and its SHA-256 digest |
| `locator` | Endpoint, CSS selector or page index per page; `complete: true/false` and the pagination bound used |
| `rows` | Raw rows as extracted: row identity, raw column text, parsed numbers, rank, and the cell locator of each value |
| `chatbot_evidence` | For `method: chatbot` only: child run ID, provider, response digest and citations |
| `quality_column` | Chosen main ranking column (owner Q3) and why |
| `direction` | `higher_better` or `lower_better`; lower values are scored as `q = -raw` |
| `score_kind` | `score` or `rank_only` (see below) |
| `dimension_columns` | Every non-quality column, mapped to the dimension registry (S6b) or kept as an unmapped raw column |
| `status` | `scored`, `dropped_too_few`, `dropped_flat`, `rank_only_unscored`, `unverified`, `extract_failed`, with reason |

Rules (review F4):
- A value counts only when it traces to a saved cell. A chatbot table is checked against accessible source content. Rows that cannot be checked stay `unverified` with a reason and are not scored.
- **Rank-only boards** (only an order, no metric) are kept and reported, but they are **not** mixed into the metric quality score (review O6). Reason: ranks 1/2/3 normalize to 100/50/0, while raw qualities 99/98/1 normalize to 100/98.98/0. A separate rank-derived score would need its own owner decision.

### S5 match (proposed, revised after review F5)

- The agent builds `matches.json`: one canonical candidate per entity, with aliases per leaderboard, method (`exact`, `normalized`, `llm`), evidence and match confidence.
- Canonical identity = vendor + product type (API, model, library) + model/version + benchmarked configuration when known.
- Normalization (case, punctuation, vendor prefix, "API"/"model" suffix) only **proposes** matches. It never proves identity. Each proposal is checked by the agent with the evidence it has.
- Two names merge only with source-supported evidence that they measure the same entity and configuration. Two vendors' products with the same name stay separate. A model and its API wrapper stay separate unless a source says they are measured the same way.
- Collisions: if two rows on one board map to one canonical candidate, the board keeps the best-evidenced row and reports the other as a duplicate.
- Versions stay separate unless a source states they are the same.
- Unresolved aliases stay separate automatically. No user step (owner Q6). Low-confidence decisions are listed in the report.

### S6 score

`eligible(L, c)` holds when L is a scored board with `w_L > 0` and c is a matched candidate with a **finite** quality value `q` on L (after direction inversion). Presence without a usable value does not count (review F2).

```
norm_L(c)     = 100 * (q_c - min_L) / (max_L - min_L)       min/max over eligible values on L
w_L           = mass_L / Σ mass over scored boards          (S3)
E(c)          = { L : eligible(L, c) }
final(c)      = Σ_{L ∈ E(c)} w_L * norm_L(c)  /  Σ_{L ∈ E(c)} w_L      (owner Q1)
confidence(c) = Σ_{L ∈ E(c)} w_L                                       (owner Q1, Q2; Σ w_L = 1)
```

- If `E(c)` is empty: `final = null`, no quality rank. The candidate may still appear in the dimensions table.
- If no board is scored: the S3 rule 3 outcome applies (no final score).
- `final` stays on 0–100 because of the renormalization. A candidate on one small leaderboard can reach 100 with a low confidence. The confidence column and the chart encoding (section 3) keep that visible.
- Meaning of `confidence`: the share of scored source weight that has a usable score for this candidate. It is not statistical certainty, extraction accuracy or match confidence. A candidate on the only scored board shows 100%. The report says this in one line.
- Ties: equal raw values get equal normalized scores.
- Rank in the final table: by `final`, ties broken by `confidence`, then by name.
- Non-quality dimensions are not part of `final`. They are context for the charts (S6b).

### S6b Extra dimensions (owner decision)

Owner: add every other dimension the sources expose, such as cost, the way artificialanalysis.ai does.

- **Dimension registry per domain (proposed, revised after review F6).** S1 asks the chatbots which dimensions matter for the domain beyond quality. For OCR, examples are price per 1,000 pages, latency, throughput, supported languages, max file size, handwriting support and self-hostable. This **seeds** the registry. S4 and official docs may add entries; each addition bumps the registry version. Unmapped raw columns are kept. Each entry has a key, a canonical unit, a type (`number`, `bool`, `category`) and a direction (`lower_better`, `higher_better` or `none`).
- **Comparable context (review F3).** Each observation stores its context: product/version, operation or tier, workload, measurement conditions, currency and date. Example: price for plain OCR and price for layout OCR are two contexts, even in the same unit. Each dimension declares one default comparable context per domain.
- **Sources and precedence.** First filter observations to the dimension's declared comparable context; out-of-context values never compete, so a high-weight out-of-context value cannot hide a comparable official value. Then order: (1) leaderboard column, higher `w_L` first; (2) the candidate's official pricing or docs page; (3) nothing. Within one rank, the newer date wins. Each value records its observation ID, URL, date, method and why it was chosen. The agent never fills a value from memory.
- **Conflicts (typed).** Bool and category: any difference is a conflict. Number: conflict when `|a - b| / max(|a|, |b|) > 0.20` (proposed display rule, not a quality guarantee); two zeros never conflict. All observations stay in `dimensions.json`.
- **Missing values** stay `null`. A chart over a dimension plots only the candidates with a value in the declared context, and it says how many it left out and why.
- **Pareto rule.** Lower-is-better axes are minimized and higher-is-better axes maximized. A point is dominated when another is at least as good on both axes and strictly better on one. Equal points are both kept. Null and nonfinite values are excluded. The frontier is labelled as computed over comparable observations only. Confidence is shown, not used as a penalty.

### S6a Too few candidates (R2, proposed)

A leaderboard contributes no scores when either holds:
- fewer than **3** distinct canonical candidates have a finite, verified quality value (after S5 duplicates are resolved). With 2 points, min-max yields only 0 and 100, which carries no information beyond order. Three points do not prove the benchmark is reliable; the rule only avoids that two-point case;
- `max_L == min_L` (division by zero).

A dropped leaderboard still appears in the report with its reason and still counts toward discovery statistics. It does not count toward weights or confidence.

## 3. Outputs and charts (owner Q8)

Run folder: `request.json`, `discovery/`, `leaderboards/`, `matches.json`, `weights.json`, `registry.json`, `dimensions.json`, `final.json`, `leaderboard.md`, `leaderboard.csv`, `report.html`.

Resume (review): each stage saves dependency versions, source digests, configuration and its schema version. Changed inputs invalidate downstream stages. Confirmed child runs of ihav-web-chat are reused, never re-sent.

`report.html` is one static file with inline data and charts, styled like artificialanalysis.ai (dark-first, clean cards, labelled points). Charts:

1. **Final score ranking**: horizontal bar of `final`; bar opacity or a side gauge shows `confidence`.
2. **Quality vs dimension scatter with Pareto frontier**: one chart per numeric dimension with a direction, for example quality vs price and quality vs latency. A selector switches dimensions. y = `final`; frontier line through non-dominated candidates; point size = confidence; labels on frontier points. Quality vs price is the headline chart when price exists.
3. **Per-dimension bar charts**: one ranked bar chart per numeric dimension, like the price and speed cards on artificialanalysis.ai.
4. **Comparison table**: candidates × quality, confidence and every registry dimension; sortable; boolean and category dimensions show as badges.
5. **Coverage grid**: candidates × leaderboards; cell = normalized score, empty when absent.
6. **Leaderboard weights**: share of total weight per leaderboard, with `weight_basis` marked.

Each chart notes how many candidates or leaderboards it omits and why. Chart implementation follows the dataviz guidance at build time.

## 4. Repo shape (owner Q7)

Same layout as the visit-counter plan (verified, its repo-plan section 3.1, the gpt-web-imagen split layout): root `.claude-plugin/marketplace.json` and `.agents/plugins/marketplace.json`; `plugins/ihav-leaderboards/` with `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `claude/skills/ihav-leaderboards/SKILL.md`, `core/ihav-leaderboards/` (Codex skill, scripts, Python package). No root `bin/` or `skills/`. Owner `hiendang7613`, MIT. Tests run offline on recorded fixtures. Only difference: `core/` adds `scoring.py`, `matching.py`, `extract/`, `render/` and an HTML template.

## 5. Open items

| ID | Item | Default used now |
|---|---|---|
| O1 | Domain collision weight | Owner kept: equal split; labelled allocated domain popularity |
| O2 | Weight for `rank_only` / no-data visits | Owner kept: floor = smallest finite positive visits; policy weight, one per domain; no-weight outcome in S3 rule 3 |
| O3 | Pareto x-axis | Resolved by owner: every numeric dimension with data, within one comparable context (S6b) |
| O4 | Too-few threshold | Owner kept: fewer than 3 distinct verified scores, or `max == min` |
| O5 | Auto-install of ihav-web-chat | **Open owner goal**, not fulfilled. v0 prints install command; mechanism to be researched |
| O6 | Rank-only leaderboards | Changed after review: reported, not mixed into the metric score |

## 6. First live run acceptance (owner decision)

The first live run, "OCR API", is the main acceptance test for the agent-driven stages, which offline tests cannot cover. It passes only when every check below holds, with evidence saved in the run folder:

1. **Discover:** every listed leaderboard has a real URL, and no URL comes from model memory. The first run may use ChatGPT alone (owner decision, 2026-10-04); the report then says one chatbot answered. Gemini joins when its adapter works.
2. **Collect:** every URL has a liveness class. Redirect duplicates take one slot.
3. **Weigh:** every selected board has a saved visit-counter result or error object; `weights.json` shows the weight basis.
4. **Extract:** every scored value traces to a saved snapshot cell. Chatbot-read rows are verified against the page or left unscored.
5. **Match:** every merge in `matches.json` has evidence. A manual spot check of 10 merges finds no wrong merge.
6. **Score and report:** `final.json`, `leaderboard.md`, `leaderboard.csv` and `report.html` exist. A manual spot check of 5 candidates reproduces their scores from the saved board values.

Any failed check becomes a bug with a regression test before the demo page is published.
