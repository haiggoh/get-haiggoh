#!/usr/bin/env python3
"""Task 3 contract: first-run state, default ticks, and route planning.

Usage: python3 -m pytest tests/tui/test_selection.py tests/tui/test_routes.py -q
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from get_haiggoh_tui.inventory import Row  # noqa: E402
from get_haiggoh_tui.routes import plan_steps  # noqa: E402
from get_haiggoh_tui.selection import default_ticks, is_first_run, mark_first_run_done  # noqa: E402


def row(name, status, section="plugin", tool=None):
    installed = None if status == "missing" else "1.0"
    latest = None if status == "missing" else ("2.0" if status == "outdated" else "1.0")
    return Row(name=name, section=section, mark="💸", description="d", adds="a",
               installed=installed, latest=latest, status=status, diagnostic=None,
               menu=None, tool=tool)


HUMAN_SHELL = {"name": "human-shell", "repo": "haiggoh/human-shell",
               "formula": "haiggoh/tap/human-shell",
               "fallback": {"kind": "release-installer", "asset": "human-shell-installer-v*.zsh"},
               "without_brew_loses": "no Dock icon", "version_cmd": None, "menu": None}

NO_FALLBACK_TOOL = {"name": "some-tool", "repo": "haiggoh/some-tool", "formula": "haiggoh/tap/some-tool",
                    "fallback": None, "without_brew_loses": None, "version_cmd": None, "menu": None}


class FirstRunTests(unittest.TestCase):
    def test_is_first_run_when_state_missing_or_corrupt(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "state.json"
            self.assertTrue(is_first_run(p))
            p.write_text("{not json")
            self.assertTrue(is_first_run(p))

    def test_mark_first_run_done_is_atomic_and_schemas(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "state.json"
            mark_first_run_done(p)
            self.assertFalse(is_first_run(p))
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(data, {"schema": 1, "first_run_done": True})

    def test_first_run_ticks_missing_and_outdated(self):
        rows = [row("a", "missing"), row("b", "outdated"), row("c", "current"),
                row("d", "unverified")]
        self.assertEqual(default_ticks(rows, first_run=True), {"a", "b"})

    def test_later_run_ticks_only_outdated(self):
        rows = [row("a", "missing"), row("b", "outdated"), row("c", "current")]
        self.assertEqual(default_ticks(rows, first_run=False), {"b"})


class PlanStepsTests(unittest.TestCase):
    def test_update_never_installs(self):
        rows = [row("a", "missing"), row("b", "outdated")]
        steps = plan_steps(rows, {"a", "b"}, "update", brew_present=True, brew_allowed=False)
        self.assertEqual([s.name for s in steps], ["b"])
        self.assertEqual(steps[0].op, "update")

    def test_bulk_uninstall_excludes_self(self):
        # self IS ticked here — the exclusion must come from plan_steps, not the test
        # (a mutant that drops the SELF_NAME filter turns this RED)
        rows = [row("get-haiggoh", "current"), row("b", "outdated"), row("c", "missing")]
        steps = plan_steps(rows, {"get-haiggoh", "b", "c"}, "uninstall",
                           brew_present=True, brew_allowed=False)
        names = [s.name for s in steps]
        self.assertNotIn("get-haiggoh", names)
        self.assertEqual(names, ["b"])  # c is missing -> not uninstallable

    def test_self_step_first(self):
        rows = [row("b", "outdated"), row("get-haiggoh", "outdated")]
        steps = plan_steps(rows, {"b", "get-haiggoh"}, "update",
                           brew_present=True, brew_allowed=False)
        self.assertEqual(steps[0].name, "get-haiggoh")
        self.assertEqual(steps[0].argv,
                         ["claude", "plugin", "update", "get-haiggoh@haiggoh"])

    def test_brew_present_prefers_formula(self):
        rows = [row("human-shell", "missing", section="tool", tool=HUMAN_SHELL)]
        steps = plan_steps(rows, {"human-shell"}, "install",
                           brew_present=True, brew_allowed=False)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].route, "brew")
        self.assertEqual(steps[0].argv, ["brew", "install", "haiggoh/tap/human-shell"])
        self.assertFalse(steps[0].needs_brew)

    def test_brew_declined_uses_fallback_with_loss_note(self):
        rows = [row("human-shell", "missing", section="tool", tool=HUMAN_SHELL)]
        steps = plan_steps(rows, {"human-shell"}, "install",
                           brew_present=False, brew_allowed=False)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].route, "release-installer")
        self.assertTrue(steps[0].needs_brew)
        self.assertIn("no Dock icon", steps[0].note or "")

    def test_brew_allowed_without_brew_marks_needs_brew(self):
        rows = [row("human-shell", "missing", section="tool", tool=HUMAN_SHELL)]
        steps = plan_steps(rows, {"human-shell"}, "install",
                           brew_present=False, brew_allowed=True)
        self.assertEqual(steps[0].route, "brew")
        self.assertTrue(steps[0].needs_brew)

    def test_free_agents_gets_two_steps(self):
        # free-agents carries formula haiggoh/tap/free-agents in catalog/plugin-extras.json
        rows = [row("free-agents", "missing")]
        steps = plan_steps(rows, {"free-agents"}, "install",
                           brew_present=True, brew_allowed=False)
        self.assertEqual(len(steps), 2)
        self.assertEqual({s.route for s in steps}, {"plugin", "brew"})
        self.assertEqual(steps[0].argv, ["claude", "plugin", "install", "free-agents@haiggoh"])
        self.assertEqual(steps[1].argv, ["brew", "install", "haiggoh/tap/free-agents"])

    def test_no_fallback_tool_is_noted_not_run(self):
        rows = [row("some-tool", "missing", section="tool", tool=NO_FALLBACK_TOOL)]
        steps = plan_steps(rows, {"some-tool"}, "install",
                           brew_present=False, brew_allowed=False)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].argv, [])
        self.assertIn("Homebrew", steps[0].note or "")

    def test_plugin_argv_verbs(self):
        rows = [row("waypoints", "missing")]
        s = plan_steps(rows, {"waypoints"}, "install", brew_present=False, brew_allowed=False)
        self.assertEqual(s[0].argv, ["claude", "plugin", "install", "waypoints@haiggoh"])
        rows = [row("waypoints", "current")]
        s = plan_steps(rows, {"waypoints"}, "uninstall", brew_present=False, brew_allowed=False)
        self.assertEqual(s[0].argv, ["claude", "plugin", "uninstall", "waypoints@haiggoh"])


if __name__ == "__main__":
    unittest.main()
