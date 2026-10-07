# OCR API (synthetic example)

Scored 4 of 5 selected leaderboards. Ranked 10 candidates.

**Synthetic example: these values demonstrate the report; they are not live benchmark evidence.**

## Warnings

- Synthetic fixture data; this report is not a live leaderboard evaluation.
- Dependency package versions were not recorded by the host.
- Legacy saved visit contracts retained without migration: bench-hub.example, doc-arena.example, ocr-league.example, paperbench.example.

Confidence is the share of scored source weight with a usable quality value, not statistical certainty or match confidence.

| # | Candidate | Score | Confidence | price | latency | handwriting |
|---|---|---|---|---|---|---|
| 1 | Cobalt Docs | 100.0 | 100% | 4.53 | 1.44 | yes |
| 2 | Ember Text | 81.0 | 100% | 3.09 | - | yes |
| 3 | Harbor OCR | 71.4 | 100% | 3.61 | 3.15 | yes |
| 4 | Juniper Lens | 66.9 | 27% | 2.44 | 2.9 | no |
| 5 | Fjord Scan | 47.5 | 100% | 3.06 | 0.95 | yes |
| 6 | Atlas OCR | 39.7 | 57% | 1.92 | 2.47 | no |
| 7 | Beacon Vision | 20.4 | 93% | 1.64 | 3.55 | yes |
| 8 | Delta Read | 10.7 | 100% | 1.65 | 0.83 | no |
| 9 | Glyph Cloud | 7.4 | 100% | 1.2 | 0.54 | no |
| 10 | Iris Parse | 0.5 | 63% | 1.16 | 3.55 | yes |

## Sources

| Leaderboard | Status | Weight | Weight basis | Domain | Domain split | Visit period | Visit source | Note |
|---|---|---|---|---|---|---|---|---|
| hub-handwriting | scored | 36.6% | domain_split(2) | bench-hub.example | 2 |  | synthetic |  |
| hub-ocr-accuracy | scored | 36.6% | domain_split(2) | bench-hub.example | 2 |  | synthetic |  |
| doc-arena | scored | 20.3% | domain_split(1) | doc-arena.example | 1 |  | synthetic |  |
| ocr-league-cer | scored | 6.5% | domain_split(1) | ocr-league.example | 1 |  | synthetic |  |
| paperbench-rank | rank_only_unscored | 0.0% | floor+domain_split(1) | paperbench.example | 1 |  | synthetic | Board gives only an order; ranks are not mixed into the metric score. |

## Discovery collection

| Leaderboard | URL | Liveness | Reason |
|---|---|---|---|
| hub-ocr-accuracy | https://bench-hub.example/hub-ocr-accuracy | live |  |
| hub-handwriting | https://bench-hub.example/hub-handwriting | live |  |
| doc-arena | https://doc-arena.example/doc-arena | live |  |
| ocr-league-cer | https://ocr-league.example/ocr-league-cer | live |  |
| paperbench-rank | https://paperbench.example/paperbench-rank | live |  |
| old-ocr-board | https://gone.example/x | dead |  |

## Live boards outside the selected group

| Leaderboard | Domain | Weight basis | Reason |
|---|---|---|---|

## Dimension sources

| Candidate | Dimension | Value | Context | Source | Observation | URL | Date | Method | Selection reason |
|---|---|---|---|---|---|---|---|---|---|
| Atlas OCR | price | 1.92 | base OCR, pay-as-you-go | official | p0 | https://example/pricing | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |
| Atlas OCR | latency | 2.47 | 1-page PDF, p50 | leaderboard | l0 |  | 2026-09-20 |  | Comparable leaderboard observation; higher scored board weight, then newer date, then observation ID. |
| Atlas OCR | handwriting | no | documented | official | h0 |  | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |
| Beacon Vision | price | 1.64 | base OCR, pay-as-you-go | official | p1 | https://example/pricing | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |
| Beacon Vision | latency | 3.55 | 1-page PDF, p50 | leaderboard | l1 |  | 2026-09-20 |  | Comparable leaderboard observation; higher scored board weight, then newer date, then observation ID. |
| Beacon Vision | handwriting | yes | documented | official | h1 |  | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |
| Cobalt Docs | price | 4.53 | base OCR, pay-as-you-go | official | p2 | https://example/pricing | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |
| Cobalt Docs | latency | 1.44 | 1-page PDF, p50 | leaderboard | l2 |  | 2026-09-20 |  | Comparable leaderboard observation; higher scored board weight, then newer date, then observation ID. |
| Cobalt Docs | handwriting | yes | documented | official | h2 |  | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |
| Delta Read | price | 1.65 | base OCR, pay-as-you-go | official | p3 | https://example/pricing | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |
| Delta Read | latency | 0.83 | 1-page PDF, p50 | leaderboard | l3 |  | 2026-09-20 |  | Comparable leaderboard observation; higher scored board weight, then newer date, then observation ID. |
| Delta Read | handwriting | no | documented | official | h3 |  | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |
| Ember Text | price | 3.09 | base OCR, pay-as-you-go | official | p4 | https://example/pricing | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |
| Ember Text | handwriting | yes | documented | official | h4 |  | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |
| Fjord Scan | price | 3.06 | base OCR, pay-as-you-go | official | p5 | https://example/pricing | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |
| Fjord Scan | latency | 0.95 | 1-page PDF, p50 | leaderboard | l5 |  | 2026-09-20 |  | Comparable leaderboard observation; higher scored board weight, then newer date, then observation ID. |
| Fjord Scan | handwriting | yes | documented | official | h5 |  | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |
| Glyph Cloud | price | 1.2 | base OCR, pay-as-you-go | official | p6 | https://example/pricing | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |
| Glyph Cloud | latency | 0.54 | 1-page PDF, p50 | leaderboard | l6 |  | 2026-09-20 |  | Comparable leaderboard observation; higher scored board weight, then newer date, then observation ID. |
| Glyph Cloud | handwriting | no | documented | official | h6 |  | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |
| Harbor OCR | price | 3.61 | base OCR, pay-as-you-go | official | p7 | https://example/pricing | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |
| Harbor OCR | latency | 3.15 | 1-page PDF, p50 | leaderboard | l7 |  | 2026-09-20 |  | Comparable leaderboard observation; higher scored board weight, then newer date, then observation ID. |
| Harbor OCR | handwriting | yes | documented | official | h7 |  | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |
| Iris Parse | price | 1.16 | base OCR, pay-as-you-go | official | p8 | https://example/pricing | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |
| Iris Parse | latency | 3.55 | 1-page PDF, p50 | leaderboard | l8 |  | 2026-09-20 |  | Comparable leaderboard observation; higher scored board weight, then newer date, then observation ID. |
| Iris Parse | handwriting | yes | documented | official | h8 |  | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |
| Juniper Lens | price | 2.44 | base OCR, pay-as-you-go | official | p9 | https://example/pricing | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |
| Juniper Lens | latency | 2.9 | 1-page PDF, p50 | leaderboard | l9 |  | 2026-09-20 |  | Comparable leaderboard observation; higher scored board weight, then newer date, then observation ID. |
| Juniper Lens | handwriting | no | documented | official | h9 |  | 2026-10-01 |  | Comparable official observation; no usable comparable leaderboard observation; newer date, then observation ID. |

## Identity matching decisions

Match confidence records identity evidence and remains separate from the score's source coverage.

| Candidate | Match confidence | Method | Evidence | Aliases |
|---|---|---|---|---|
| Cobalt Docs | high |  | Synthetic: identical names. | [{&quot;board&quot;: &quot;hub-ocr-accuracy&quot;, &quot;name&quot;: &quot;Cobalt Docs&quot;}, {&quot;board&quot;: &quot;hub-handwriting&quot;, &quot;name&quot;: &quot;Cobalt Docs&quot;}, {&quot;board&quot;: &quot;doc-arena&quot;, &quot;name&quot;: &quot;Cobalt Docs&quot;}, {&quot;board&quot;: &quot;ocr-league-cer&quot;, &quot;name&quot;: &quot;Cobalt Docs&quot;}, {&quot;board&quot;: &quot;paperbench-rank&quot;, &quot;name&quot;: &quot;Cobalt Docs&quot;}] |
| Ember Text | high |  | Synthetic: identical names. | [{&quot;board&quot;: &quot;hub-ocr-accuracy&quot;, &quot;name&quot;: &quot;Ember Text&quot;}, {&quot;board&quot;: &quot;hub-handwriting&quot;, &quot;name&quot;: &quot;Ember Text&quot;}, {&quot;board&quot;: &quot;doc-arena&quot;, &quot;name&quot;: &quot;Ember Text&quot;}, {&quot;board&quot;: &quot;ocr-league-cer&quot;, &quot;name&quot;: &quot;Ember Text&quot;}, {&quot;board&quot;: &quot;paperbench-rank&quot;, &quot;name&quot;: &quot;Ember Text&quot;}] |
| Harbor OCR | high |  | Synthetic: identical names. | [{&quot;board&quot;: &quot;hub-ocr-accuracy&quot;, &quot;name&quot;: &quot;Harbor OCR&quot;}, {&quot;board&quot;: &quot;hub-handwriting&quot;, &quot;name&quot;: &quot;Harbor OCR&quot;}, {&quot;board&quot;: &quot;doc-arena&quot;, &quot;name&quot;: &quot;Harbor OCR&quot;}, {&quot;board&quot;: &quot;ocr-league-cer&quot;, &quot;name&quot;: &quot;Harbor OCR&quot;}, {&quot;board&quot;: &quot;paperbench-rank&quot;, &quot;name&quot;: &quot;Harbor OCR&quot;}] |
| Juniper Lens | high |  | Synthetic: identical names. | [{&quot;board&quot;: &quot;hub-ocr-accuracy&quot;, &quot;name&quot;: &quot;Juniper Lens&quot;}, {&quot;board&quot;: &quot;hub-handwriting&quot;, &quot;name&quot;: &quot;Juniper Lens&quot;}, {&quot;board&quot;: &quot;doc-arena&quot;, &quot;name&quot;: &quot;Juniper Lens&quot;}, {&quot;board&quot;: &quot;ocr-league-cer&quot;, &quot;name&quot;: &quot;Juniper Lens&quot;}, {&quot;board&quot;: &quot;paperbench-rank&quot;, &quot;name&quot;: &quot;Juniper Lens&quot;}] |
| Fjord Scan | high |  | Synthetic: identical names. | [{&quot;board&quot;: &quot;hub-ocr-accuracy&quot;, &quot;name&quot;: &quot;Fjord Scan&quot;}, {&quot;board&quot;: &quot;hub-handwriting&quot;, &quot;name&quot;: &quot;Fjord Scan&quot;}, {&quot;board&quot;: &quot;doc-arena&quot;, &quot;name&quot;: &quot;Fjord Scan&quot;}, {&quot;board&quot;: &quot;ocr-league-cer&quot;, &quot;name&quot;: &quot;Fjord Scan&quot;}, {&quot;board&quot;: &quot;paperbench-rank&quot;, &quot;name&quot;: &quot;Fjord Scan&quot;}] |
| Atlas OCR | high |  | Synthetic: identical names. | [{&quot;board&quot;: &quot;hub-ocr-accuracy&quot;, &quot;name&quot;: &quot;Atlas OCR&quot;}, {&quot;board&quot;: &quot;hub-handwriting&quot;, &quot;name&quot;: &quot;Atlas OCR&quot;}, {&quot;board&quot;: &quot;doc-arena&quot;, &quot;name&quot;: &quot;Atlas OCR&quot;}, {&quot;board&quot;: &quot;ocr-league-cer&quot;, &quot;name&quot;: &quot;Atlas OCR&quot;}, {&quot;board&quot;: &quot;paperbench-rank&quot;, &quot;name&quot;: &quot;Atlas OCR&quot;}] |
| Beacon Vision | high |  | Synthetic: identical names. | [{&quot;board&quot;: &quot;hub-ocr-accuracy&quot;, &quot;name&quot;: &quot;Beacon Vision&quot;}, {&quot;board&quot;: &quot;hub-handwriting&quot;, &quot;name&quot;: &quot;Beacon Vision&quot;}, {&quot;board&quot;: &quot;doc-arena&quot;, &quot;name&quot;: &quot;Beacon Vision&quot;}, {&quot;board&quot;: &quot;ocr-league-cer&quot;, &quot;name&quot;: &quot;Beacon Vision&quot;}, {&quot;board&quot;: &quot;paperbench-rank&quot;, &quot;name&quot;: &quot;Beacon Vision&quot;}] |
| Delta Read | high |  | Synthetic: identical names. | [{&quot;board&quot;: &quot;hub-ocr-accuracy&quot;, &quot;name&quot;: &quot;Delta Read&quot;}, {&quot;board&quot;: &quot;hub-handwriting&quot;, &quot;name&quot;: &quot;Delta Read&quot;}, {&quot;board&quot;: &quot;doc-arena&quot;, &quot;name&quot;: &quot;Delta Read&quot;}, {&quot;board&quot;: &quot;ocr-league-cer&quot;, &quot;name&quot;: &quot;Delta Read&quot;}, {&quot;board&quot;: &quot;paperbench-rank&quot;, &quot;name&quot;: &quot;Delta Read&quot;}] |
| Glyph Cloud | high |  | Synthetic: identical names. | [{&quot;board&quot;: &quot;hub-ocr-accuracy&quot;, &quot;name&quot;: &quot;Glyph Cloud&quot;}, {&quot;board&quot;: &quot;hub-handwriting&quot;, &quot;name&quot;: &quot;Glyph Cloud&quot;}, {&quot;board&quot;: &quot;doc-arena&quot;, &quot;name&quot;: &quot;Glyph Cloud&quot;}, {&quot;board&quot;: &quot;ocr-league-cer&quot;, &quot;name&quot;: &quot;Glyph Cloud&quot;}, {&quot;board&quot;: &quot;paperbench-rank&quot;, &quot;name&quot;: &quot;Glyph Cloud&quot;}] |
| Iris Parse | high |  | Synthetic: identical names. | [{&quot;board&quot;: &quot;hub-ocr-accuracy&quot;, &quot;name&quot;: &quot;Iris Parse&quot;}, {&quot;board&quot;: &quot;hub-handwriting&quot;, &quot;name&quot;: &quot;Iris Parse&quot;}, {&quot;board&quot;: &quot;doc-arena&quot;, &quot;name&quot;: &quot;Iris Parse&quot;}, {&quot;board&quot;: &quot;ocr-league-cer&quot;, &quot;name&quot;: &quot;Iris Parse&quot;}, {&quot;board&quot;: &quot;paperbench-rank&quot;, &quot;name&quot;: &quot;Iris Parse&quot;}] |

## Source fingerprints

| Saved source | SHA-256 |
|---|---|
| snapshots/dimensions.json | e6c407d9fadb4534288cea6aa6f7e834387e16d48d979737e7c0f339e9d1309a |
| snapshots/doc-arena.json | f7659ecc844fe14b194a1d17bb461a289bb62ad752c0bf0ece5d6855133337a6 |
| snapshots/hub-handwriting.json | cbafd66b2aff6b498e7bcf4f40355845c0b7c36f5a7a45eff4b3fb9892a72c2a |
| snapshots/hub-ocr-accuracy.json | 62a4fae958f09069bbcc7fc6d39535e2fcc19c08850d4d421d24c68731819cdd |
| snapshots/ocr-league-cer.json | 1e88e468ec95ce02d9994ab6487d8930bfb4d8e8e881167dc9d954552fe240d3 |
| snapshots/paperbench-rank.json | a9fd7a56bc611d7749ad7b908331d74ae6eff93245e0660dbae34ef90b0076c9 |

- confidence = share of scored source weight with a usable score for this candidate; it is not statistical certainty, extraction accuracy or match confidence.
- Weights are allocated domain popularity, not page visits.
