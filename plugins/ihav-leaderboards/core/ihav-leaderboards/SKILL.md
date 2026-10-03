---
name: ihav-leaderboards
description: Build one quality-first leaderboard for a product or model category (for example OCR APIs, speech-to-text, text-to-image) by finding the most-visited public leaderboards, extracting their tables and merging the scores with visit-based weights, confidence, cost dimensions and Pareto charts. Use when someone asks which tool, API or model is best in a category, or asks to compare or merge leaderboards.
---

# ihav-leaderboards

Follow [the workflow](references/workflow.md) stage by stage. Replace `<skill-directory>` with the installed directory that contains this `SKILL.md`.

On macOS/Linux, use `python3`. On Windows, use `py -3`:

```bash
python3 <skill-directory>/scripts/leaderboards.py new "OCR API"
python3 <skill-directory>/scripts/leaderboards.py weigh <run-folder>
python3 <skill-directory>/scripts/leaderboards.py score <run-folder>
```

```powershell
py -3 <skill-directory>/scripts/leaderboards.py score <run-folder>
```

Rules that always apply:

- Before discovery and weighting, check that ihav-web-chat and ihav-web-visit-counter are installed (workflow stage 0). If one is missing, print its install command and stop.
- Never fill a gap from memory. A missing value stays `null` with a reason.
- On HTTP 401, 403, 429, a captcha or a bot wall, stop using that source. Do not try another browser, proxy or route to get past it.
- If `weigh` or `score` exits with code 2, report the diagnostic. Do not fall back to equal weights.
- Match candidate names yourself and record every decision in `matches.json`. Do not ask the user to match names.
- `confidence` is the share of scored source weight behind a score, not statistical certainty.
- Keep all run files under `.ihav_space/ihav-leaderboards/`.
