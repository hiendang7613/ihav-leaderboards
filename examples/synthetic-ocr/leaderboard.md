# OCR API (synthetic example)

Scored 4 of 5 selected leaderboards. Ranked 10 candidates.

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

| Leaderboard | Status | Weight | Note |
|---|---|---|---|
| hub-handwriting | scored | 36.6% |  |
| hub-ocr-accuracy | scored | 36.6% |  |
| doc-arena | scored | 20.3% |  |
| ocr-league-cer | scored | 6.5% |  |
| paperbench-rank | rank_only_unscored | 0.0% | Board gives only an order; ranks are not mixed into the metric score. |

- confidence = share of scored source weight with a usable score for this candidate; it is not statistical certainty, extraction accuracy or match confidence.
- Weights are allocated domain popularity, not page visits.
