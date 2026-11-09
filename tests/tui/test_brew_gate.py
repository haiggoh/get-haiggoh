#!/usr/bin/env python3
"""Task 4 contract: the 🍺 Homebrew gate — notice copy, decline lines, verification.

Usage: python3 -m pytest tests/tui/test_brew_gate.py -q
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from get_haiggoh_tui import brew_gate as bg  # noqa: E402
from get_haiggoh_tui.inventory import Row  # noqa: E402
from get_haiggoh_tui.routes import Step  # noqa: E402


def row(name, mark="💸", section="plugin", tool=None):
    return Row(name=name, section=section, mark=mark, description="d", adds="a",
               installed=None, latest=None, status="missing", diagnostic=None,
               menu=None, tool=tool)


HUMAN_SHELL = {"name": "human-shell", "repo": "haiggoh/human-shell",
               "formula": "haiggoh/tap/human-shell",
               "fallback": {"kind": "release-installer", "asset": "human-shell-installer-v*.zsh"},
               "without_brew_loses": "no Dock icon", "version_cmd": None, "menu": None}


def step(name, needs_brew, route="brew"):
    return Step(name=name, op="install", route=route, argv=[], needs_brew=needs_brew, note=None)


class NeedsBrewTests(unittest.TestCase):
    def test_no_notice_when_brew_present(self):
        self.assertEqual(bg.needs_brew([step("a", False), step("b", False)]), [])

    def test_collects_and_dedupes_names(self):
        steps = [step("free-agents", True, "plugin"), step("free-agents", True, "brew"),
                 step("human-shell", True), step("waypoints", False)]
        self.assertEqual(bg.needs_brew(steps), ["free-agents", "human-shell"])


class NoticeTests(unittest.TestCase):
    def test_notice_exact_copy_three_names(self):
        text = bg.notice_text(["free-agents", "human-shell", "claude-code-transcript-distiller"])
        self.assertEqual(
            text,
            "🍺 Homebrew will be installed now — it makes future updates of "
            "free-agents, human-shell and claude-code-transcript-distiller easier. "
            "It asks for your Mac password once.")

    def test_notice_joins_two_and_one(self):
        self.assertIn("a and b easier", bg.notice_text(["a", "b"]))
        self.assertIn("solo easier", bg.notice_text(["solo"]))

    def test_buttons_exact(self):
        self.assertEqual(bg.BUTTONS, ("Install 🍺 Homebrew", "Continue without 🍺 Homebrew"))

    def test_install_argv_is_the_official_one_liner_under_bash(self):
        self.assertEqual(bg.INSTALL_ARGV[0:2], ["/bin/bash", "-c"])
        self.assertIn("raw.githubusercontent.com/Homebrew/install/HEAD/install.sh",
                      bg.INSTALL_ARGV[2])
        self.assertIn("$(curl", bg.INSTALL_ARGV[2])  # $(…) must expand at run time


class DeclineTests(unittest.TestCase):
    def test_decline_names_the_loss(self):
        rows = [row("human-shell", mark="🤝", section="tool", tool=HUMAN_SHELL)]
        lines = bg.decline_lines(rows, ["human-shell"])
        self.assertEqual(len(lines), 1)
        self.assertIn("🤝 human-shell: continuing via release-installer", lines[0])
        self.assertIn("no Dock icon", lines[0])

    def test_decline_plugin_without_formula_uses_plugin_route(self):
        rows = [row("waypoints", mark="🧭")]
        lines = bg.decline_lines(rows, ["waypoints"])
        self.assertIn("continuing via plugin", lines[0])


class VerifyTests(unittest.TestCase):
    def test_verify_rechecks_after_run(self):
        # brew_path flips only after the fake installer ran -> verify must re-check, not assume
        state = {"present": False}
        with mock.patch.object(bg, "brew_path", lambda: "/opt/homebrew/bin/brew" if state["present"] else None):
            self.assertFalse(bg.verify_installed())   # before the run
            state["present"] = True                    # the fake installer "installed" it
            self.assertTrue(bg.verify_installed())    # re-checked after


if __name__ == "__main__":
    unittest.main()
