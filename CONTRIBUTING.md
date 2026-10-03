# Contributing

1. Keep the core on the Python standard library and Python 3.9+.
2. The `weigh` and `score` commands make no network calls. Agent-driven steps live in `references/workflow.md`.
3. Add a test for every rule change. Run `python3 -m unittest discover -s tests -t tests`; all tests run offline.
4. Keep both `SKILL.md` files in sync. `tests/test_plugin_files.py` checks the shared rules.
5. Bump the version in both `plugin.json` files and in `ihav_leaderboards/__init__.py` together, and add a CHANGELOG entry.
6. Never add a value from memory to fixtures. Label synthetic data as synthetic.
