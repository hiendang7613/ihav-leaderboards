from __future__ import annotations

import json
import unittest

from helpers import CORE, PLUGIN, ROOT

import ihav_leaderboards


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class ManifestTests(unittest.TestCase):
    def test_host_manifests_share_name_version_and_license(self):
        claude = load(PLUGIN / ".claude-plugin/plugin.json")
        codex = load(PLUGIN / ".codex-plugin/plugin.json")
        self.assertEqual(claude["name"], codex["name"])
        self.assertEqual(claude["name"], "ihav-leaderboards")
        self.assertEqual(claude["version"], codex["version"])
        self.assertEqual(claude["version"], ihav_leaderboards.__version__)
        self.assertEqual(claude["license"], codex["license"])
        self.assertEqual(claude["license"], "MIT")

    def test_claude_dependency_comes_from_the_ihav_catalog(self):
        claude = load(PLUGIN / ".claude-plugin/plugin.json")
        codex = load(PLUGIN / ".codex-plugin/plugin.json")
        self.assertEqual(claude["dependencies"], [{"name": "ihav-web-visit-counter", "marketplace": "ihav"}])
        self.assertNotIn("dependencies", codex)
        market = load(ROOT / ".claude-plugin/marketplace.json")
        self.assertEqual(market["allowCrossMarketplaceDependenciesOn"], ["ihav"])

    def test_both_marketplaces_point_to_the_plugin_and_skill_paths_exist(self):
        claude_market = load(ROOT / ".claude-plugin/marketplace.json")
        codex_market = load(ROOT / ".agents/plugins/marketplace.json")
        self.assertEqual(claude_market["plugins"][0]["source"], "./plugins/ihav-leaderboards")
        self.assertEqual(codex_market["plugins"][0]["source"]["path"], "./plugins/ihav-leaderboards")
        self.assertTrue((PLUGIN / "claude/skills/ihav-leaderboards/SKILL.md").is_file())
        self.assertTrue((CORE / "SKILL.md").is_file())
        self.assertFalse((ROOT / "skills").exists())
        self.assertFalse((ROOT / "bin").exists())


class SkillTests(unittest.TestCase):
    def test_both_skills_carry_the_same_rules(self):
        claude = (PLUGIN / "claude/skills/ihav-leaderboards/SKILL.md").read_text(encoding="utf-8")
        codex = (CORE / "SKILL.md").read_text(encoding="utf-8")
        workflow = (CORE / "references/workflow.md").read_text(encoding="utf-8")
        for phrase in (
            "Never fill a gap from memory",
            "HTTP 401, 403, 429",
            "Do not try another browser",
            "Do not fall back to equal weights",
            "Do not ask the user to match names",
            "not statistical certainty",
            ".ihav_space/ihav-leaderboards/",
            "py -3",
            "workflow stage 0",
            "Never print an `ihav-web-chat@ihav` command",
            "`--dry-run` first",
            "Never resend a chatbot request",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, claude)
                self.assertIn(phrase, codex)
        self.assertIn("exit code 4) is never retried", workflow)
        self.assertIn("Rank-only boards are reported but not scored", workflow)
        self.assertNotIn("<plugin>@ihav", workflow)
        self.assertNotIn("ihav-web-chat@ihav`", workflow.replace("Do not print an `ihav-web-chat@ihav` command", ""))
        for phrase in ("--dry-run --json", "run lookup --request-key", "delivery read", "--include-text",
                       "sent_unknown", "Exit code 4 means the wait timed out", "has no command that sends it"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, workflow)

    def test_skill_links_resolve(self):
        claude_link = PLUGIN / "claude/skills/ihav-leaderboards/../../../core/ihav-leaderboards/references/workflow.md"
        self.assertTrue(claude_link.resolve().is_file())
        self.assertTrue((CORE / "references/workflow.md").is_file())

    def test_claude_skill_allows_only_the_bundled_command(self):
        claude = (PLUGIN / "claude/skills/ihav-leaderboards/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/core/ihav-leaderboards/scripts/leaderboards.py *)",
                      claude)


if __name__ == "__main__":
    unittest.main()
