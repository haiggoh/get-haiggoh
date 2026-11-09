#!/usr/bin/env python3
"""Task 7 contract: Textual app pilot tests. Run with the TUI venv python so a skip
cannot read green:  ~/.local/share/get-haiggoh/tui-venv/bin/python -m pytest tests/tui/test_app_pilot.py -rs -q
(the module importorskips textual; under the venv there must be 0 skipped).

Usage: python3 -m pytest tests/tui/test_app_pilot.py -q
"""
import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

textual = pytest.importorskip("textual")  # venv run: 0 skipped is the receipt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from get_haiggoh_tui.app import GetHaiggohApp  # noqa: E402
from get_haiggoh_tui.inventory import Row  # noqa: E402
from get_haiggoh_tui.menuspec import BACK_LABEL  # noqa: E402
from get_haiggoh_tui.runner import StepResult  # noqa: E402
from get_haiggoh_tui import screens as scr  # noqa: E402


def row(name, status, section="plugin", installed=None, latest=None, tool=None, menu=None, mark="💸", adds="a", description="d"):
    if installed is None and status != "missing":
        installed = "1.0"
    if latest is None and status in ("current", "unverified"):
        latest = installed or "1.0"
    if status == "outdated" and latest is None:
        latest = "2.0"
    return Row(name=name, section=section, mark=mark, description=description, adds=adds,
               installed=installed, latest=latest, status=status, diagnostic=None,
               menu=menu, tool=tool)


HUMAN_SHELL = {"name": "human-shell", "repo": "haiggoh/human-shell",
               "formula": "haiggoh/tap/human-shell",
               "fallback": {"kind": "release-installer", "asset": "human-shell-installer-v*.zsh"},
               "without_brew_loses": "no Dock icon", "version_cmd": None, "menu": None}

SPEC = json.loads((ROOT / "tests" / "tui" / "fixtures" / "menu-spec-valid.json").read_text())


def make_rows():
    return [
        row("get-haiggoh", "current", installed="0.9.4", latest="0.9.4", mark="👨🏻‍💻", adds="manager"),
        row("waypoints", "outdated", installed="0.14.3", latest="0.15.0", mark="🧭", adds="1 skill · hook"),
        row("cost-tracker", "missing", mark="💸", adds="1 skill · SessionEnd hook"),
        row("free-agents", "unverified", installed="0.55.7", mark="📡🦾"),
        row("human-shell", "missing", section="tool", tool=HUMAN_SHELL, mark="🤝",
            adds="brew formula · Dock launchers", description="visible outcomes"),
        row("mac-claude-migration", "current", section="tool",
            tool={"name": "mac-claude-migration", "repo": "haiggoh/mac-claude-migration",
                  "formula": "haiggoh/tap/mac-claude-migration", "fallback": {"kind": "git"},
                  "without_brew_loses": None, "version_cmd": None,
                  "menu": {"argv": ["./backup.sh"], "spec_min_version": None, "return_to_min_version": None}},
            installed="0.1.5", latest="0.1.5", mark="📦", menu={"argv": ["./backup.sh"], "spec_min_version": None, "return_to_min_version": None}),
    ]


class FakeRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, steps, **kw):
        self.calls.append([s.name for s in steps])
        return [StepResult(s, True, "ok") for s in steps]


def make_app(tmp, rows=None, brew_present=True, menu_for=None, legacy_runner=None,
             installer_runner=None, verify_installed=None, execv=None, runner=None,
             resume=False, suspend_fn=None):
    return GetHaiggohApp(
        rows_loader=lambda cached: (rows if rows is not None else make_rows()),
        runner=runner or FakeRunner(),
        state_path=Path(tmp) / "state.json",
        pending_path=Path(tmp) / "pending.json",
        brew_present=brew_present,
        resume=resume,
        menu_for=menu_for or (lambda r: ("none", None)),
        legacy_runner=legacy_runner or (lambda argv: None),
        installer_runner=installer_runner or (lambda argv: 0),
        verify_installed=verify_installed or (lambda: True),
        execv=execv,
        suspend_fn=suspend_fn,
    )


def run(coro):
    return asyncio.run(coro)


class PilotTests(unittest.TestCase):
    def test_first_launch_ticks_missing_and_outdated(self):
        with tempfile.TemporaryDirectory() as d:
            app = make_app(d)
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    return set(app.ticks)
            ticks = run(go())
            self.assertIn("waypoints", ticks)   # outdated
            self.assertIn("cost-tracker", ticks)  # missing
            self.assertIn("human-shell", ticks)   # missing tool
            self.assertNotIn("get-haiggoh", ticks)  # current
            # first run marked done after first paint
            from get_haiggoh_tui.selection import is_first_run
            self.assertFalse(is_first_run(Path(d) / "state.json"))

    def test_later_launch_ticks_only_outdated(self):
        with tempfile.TemporaryDirectory() as d:
            from get_haiggoh_tui.selection import mark_first_run_done
            mark_first_run_done(Path(d) / "state.json")
            app = make_app(d)
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    return set(app.ticks)
            self.assertEqual(run(go()), {"waypoints"})

    def test_row_label_has_mark_name_installed_status(self):
        with tempfile.TemporaryDirectory() as d:
            app = make_app(d)
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    ol = app.screen.query_one("#rows")
                    idx = next(i for i in range(ol.option_count)
                               if "free-agents" in str(ol.get_option_at_index(i).prompt))
                    label = str(ol.get_option_at_index(idx).prompt)
                    app.show_info_for("free-agents")
                    await pilot.pause()
                    return label, app.info_text()
            label, info = run(go())
            self.assertIn("📡🦾", label)          # brand mark in the row
            self.assertIn("free-agents", label)
            self.assertIn("0.55.7", label)         # installed column
            self.assertIn("? unverified", label)   # status column
            self.assertTrue(info.startswith("📡🦾 free-agents"), info)

    def test_refresh_failure_shows_in_summary_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            def loader(cached):
                if cached:
                    return make_rows()
                raise RuntimeError("network down")
            app = make_app(d)
            app.rows_loader = loader
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.pause()
                    return app.summary
            s = run(go())
            self.assertIn("couldn't check for updates", s)

    def test_summary_counts(self):
        with tempfile.TemporaryDirectory() as d:
            app = make_app(d)
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    return app.summary
            s = run(go())
            self.assertIn("1 updates available", s)
            self.assertIn("2 not installed", s)

    def test_unverified_row_shows_question_mark(self):
        with tempfile.TemporaryDirectory() as d:
            app = make_app(d)
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    labels = [str(app.screen.query_one("#rows").get_option_at_index(i).prompt)
                              for i in range(app.screen.query_one("#rows").option_count)]
                    return labels
            labels = run(go())
            self.assertTrue(any("? unverified" in lbl for lbl in labels), labels)

    def test_info_box_follows_highlight(self):
        with tempfile.TemporaryDirectory() as d:
            app = make_app(d)
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    ol = app.screen.query_one("#rows")
                    idx = next(i for i in range(ol.option_count)
                               if "cost-tracker" in str(ol.get_option_at_index(i).prompt))
                    ol.highlighted = idx
                    ol.post_message(textual.widgets.OptionList.OptionHighlighted(
                        ol, ol.get_option_at_index(idx), idx))
                    await pilot.pause()
                    return app.info_text()
            text = run(go())
            self.assertIn("cost-tracker", text)
            self.assertIn("Adds:", text)

    def test_info_box_shows_route_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            app = make_app(d)
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    app.show_info_for("human-shell")
                    await pilot.pause()
                    return app.info_text()
            text = run(go())
            self.assertIn("Installs via", text)
            self.assertIn("brew", text)

    def test_install_button_count_follows_ticks(self):
        with tempfile.TemporaryDirectory() as d:
            app = make_app(d)
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    b = app.screen.query_one("#btn-install")
                    first = str(b.label)
                    app.ticks.discard("cost-tracker")
                    app.refresh_buttons()
                    await pilot.pause()
                    return first, str(app.screen.query_one("#btn-install").label)
            first, second = run(go())
            self.assertIn("2", first)   # cost-tracker + human-shell ticked missing
            self.assertIn("1", second)

    def test_brew_notice_shown_only_when_needed(self):
        with tempfile.TemporaryDirectory() as d:
            # brew absent + a ticked brew-needing tool -> notice on install
            app = make_app(d, brew_present=False)
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("i")
                    await pilot.pause()
                    return type(app.screen).__name__
            self.assertEqual(run(go()), "BrewNoticeScreen")
        with tempfile.TemporaryDirectory() as d:
            app = make_app(d, brew_present=True)  # brew present -> no notice
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("i")
                    await pilot.pause()
                    return type(app.screen).__name__
            self.assertNotEqual(run(go()), "BrewNoticeScreen")

    def test_decline_continues_with_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            app = make_app(d, brew_present=False)
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("i")
                    await pilot.pause()
                    assert isinstance(app.screen, scr.BrewNoticeScreen)
                    await pilot.press("c")  # Continue without Homebrew
                    await pilot.pause()
                    return app.decline_lines, type(app.screen).__name__
            lines, screen = run(go())
            self.assertTrue(any("human-shell" in ln and "no Dock icon" in ln for ln in lines), lines)
            self.assertNotEqual(screen, "BrewNoticeScreen")

    def test_brew_install_runs_suspended_then_verifies(self):
        with tempfile.TemporaryDirectory() as d:
            suspended = []
            app = make_app(d, brew_present=False, verify_installed=lambda: False,
                           suspend_fn=lambda: _Suspend(suspended))  # installer "fails"
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("i")
                    await pilot.pause()
                    await pilot.press("enter")  # Install Homebrew
                    await pilot.pause()
                    return suspended, app.decline_lines, app.brew_present
            sus, lines, present = run(go())
            self.assertTrue(sus, "installer must run under App.suspend()")
            self.assertFalse(present, "verify_installed() False must NOT count as success")
            self.assertTrue(lines, "decline path after failed verify")

    def test_uninstall_confirm_lists_adds(self):
        with tempfile.TemporaryDirectory() as d:
            app = make_app(d)
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("x")
                    await pilot.pause()
                    return type(app.screen).__name__, app.screen.confirm_text
            name, text = run(go())
            self.assertEqual(name, "ConfirmScreen")
            self.assertIn("waypoints", text)
            self.assertIn("1 skill · hook", text)  # its adds

    def test_self_single_uninstall_extra_warning(self):
        with tempfile.TemporaryDirectory() as d:
            app = make_app(d)
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    app.ticks = {"get-haiggoh"}
                    await pilot.press("x")
                    await pilot.pause()
                    return type(app.screen).__name__, getattr(app.screen, "warning_text", "")
            name, text = run(go())
            self.assertIn("removes this manager", text)

    def test_leftover_pending_shows_resume_screen(self):
        with tempfile.TemporaryDirectory() as d:
            from get_haiggoh_tui.runner import write_pending
            write_pending(Path(d) / "pending.json", "update", ["waypoints"])
            app = make_app(d)
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    return type(app.screen).__name__
            self.assertEqual(run(go()), "ResumeScreen")

    def test_enter_legacy_suspends_and_returns_to_row(self):
        with tempfile.TemporaryDirectory() as d:
            ran = []
            suspended = []
            app = make_app(d, brew_present=True,
                           menu_for=lambda r: ("legacy", ["./backup.sh"]) if r.name == "mac-claude-migration" else ("none", None),
                           legacy_runner=lambda argv: ran.append(list(argv)),
                           suspend_fn=lambda: _Suspend(suspended))
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    ol = app.screen.query_one("#rows")
                    idx = next(i for i in range(ol.option_count)
                               if "mac-claude-migration" in str(ol.get_option_at_index(i).prompt))
                    ol.highlighted = idx
                    await pilot.press("enter")
                    await pilot.pause()
                    return ran, ol.highlighted, idx
            ran, hl, idx = run(go())
            self.assertEqual(ran, [["./backup.sh"]])
            self.assertTrue(suspended, "legacy hand-off must run under App.suspend()")
            self.assertEqual(hl, idx, "return to the same highlighted row")

    def test_enter_spec_menu_back_is_last(self):
        with tempfile.TemporaryDirectory() as d:
            app = make_app(d, brew_present=True,
                           menu_for=lambda r: ("spec", SPEC) if r.name == "mac-claude-migration" else ("none", None))
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    ol = app.screen.query_one("#rows")
                    idx = next(i for i in range(ol.option_count)
                               if "mac-claude-migration" in str(ol.get_option_at_index(i).prompt))
                    ol.highlighted = idx
                    await pilot.press("enter")
                    await pilot.pause()
                    return app.screen
            screen = run(go())
            self.assertIsInstance(screen, scr.ItemMenuScreen)
            self.assertEqual(screen.actions[-1]["label"], BACK_LABEL)


class DesignTests(unittest.TestCase):
    def test_theme_matches_csl_current_design(self):
        # user 2026-11-09: no grey tooltip box; CSL-current overall design
        import re
        css = (ROOT / "get_haiggoh_tui" / "theme.tcss").read_text(encoding="utf-8")
        m = re.search(r"#info\s*\{([^}]*)\}", css)
        self.assertIsNotNone(m, "#info rule must exist")
        self.assertIn("border: none", m.group(1), "the grey frame is gone")
        self.assertNotIn("ansi_bright_black", m.group(1).split("color")[-1] if "color" in m.group(1) else m.group(1))
        with tempfile.TemporaryDirectory() as d:
            app = make_app(d)
            self.assertEqual(app.theme, "textual-ansi")
            self.assertTrue(app.ansi_color)


class _Suspend:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        self.log.append("suspend")
        return self

    def __exit__(self, *a):
        return False


if __name__ == "__main__":
    unittest.main()
