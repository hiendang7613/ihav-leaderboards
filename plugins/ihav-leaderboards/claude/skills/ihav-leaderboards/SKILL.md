---
name: ihav-leaderboards
description: Build one quality-first leaderboard for a product or model category (for example OCR APIs, speech-to-text, text-to-image) by finding the most-visited public leaderboards, extracting their tables and merging the scores with visit-based weights, confidence, cost dimensions and Pareto charts. Use when someone asks which tool, API or model is best in a category, or asks to compare or merge leaderboards.
argument-hint: <category, for example "OCR API">
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/core/ihav-leaderboards/scripts/leaderboards.py *)
---

# ihav-leaderboards

Follow [the workflow](../../../core/ihav-leaderboards/references/workflow.md) stage by stage for the category `$ARGUMENTS`. The bundled command is:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/core/ihav-leaderboards/scripts/leaderboards.py" new "$ARGUMENTS"
python3 "${CLAUDE_PLUGIN_ROOT}/core/ihav-leaderboards/scripts/leaderboards.py" weigh <run-folder>
python3 "${CLAUDE_PLUGIN_ROOT}/core/ihav-leaderboards/scripts/leaderboards.py" score <run-folder>
python3 "${CLAUDE_PLUGIN_ROOT}/core/ihav-leaderboards/scripts/leaderboards.py" render <run-folder>
python3 "${CLAUDE_PLUGIN_ROOT}/core/ihav-leaderboards/scripts/leaderboards.py" verify <run-folder> --json
```

On Windows, use `py -3` instead of `python3`.

Rules that always apply:

- Before discovery and weighting, check that ihav-web-chat and ihav-web-visit-counter are installed (workflow stage 0). If ihav-web-visit-counter is missing, print its install command and stop. ihav-web-chat is not in the ihav catalog yet: if it is missing, say so and stop before discovery. Never print an `ihav-web-chat@ihav` command.
- Preview every ihav-web-chat run with `--dry-run` first. Show the user the exact prompt and providers, and queue the run only after the user approves that prompt. A queued run is not a sent prompt.
- Never resend a chatbot request. Reuse an earlier run through its request key, also after `sent_unknown` or a timeout.
- Never fill a gap from memory. A missing value stays `null` with a reason.
- On HTTP 401, 403, 429, a captcha or a bot wall, stop using that source. Do not try another browser, proxy or route to get past it.
- Exit 2 can mean a busy run: if the message says another writer holds it, wait until that writer finishes and retry only the local command; do not edit inputs or resend requests. Otherwise report the diagnostic for `weigh`/`score` and the stale/incomplete reason for `render`/`verify`. Do not fall back to equal weights.
- Match candidate names yourself and record every decision in `matches.json`. Do not ask the user to match names.
- `confidence` is the share of scored source weight behind a score, not statistical certainty.
- Keep all run files under `.ihav_space/ihav-leaderboards/`.
