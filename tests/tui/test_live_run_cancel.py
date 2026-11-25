#!/usr/bin/env python3
"""Task 7 pilot contract: Esc during a run opens "Cancel the run? y/n"; Yes leads to
the mode dialog (finish current item / immediate, with the B7 warning); double-Esc
within 0.5 s = immediate cancel; ctrl+q is blocked while running; Esc outside a run
still leaves the mode.

Run ONLY under the TUI venv python:
  ~/.local/share/get-haiggoh/tui-venv/bin/python -m pytest tests/tui/test_live_run_cancel.py -q -rs
"""
import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

textual = pytest.importorskip("textual")  # venv run: 0 skipped is the receipt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from textual.widgets import Static  # noqa: E402

from get_haiggoh_tui import screens as scr  # noqa: E402
from tests.tui.live_rig import GatedRunner  # noqa: E402
from tests.tui.test_app_pilot import make_app, row  # noqa: E402
from tests.tui.test_live_run import _wait_done, _wait_started  # noqa: E402

TWO_OUTDATED = [row("waypoints", "outdated", installed="0.14.3", latest="0.15.0"),
                row("cost-tracker", "outdated", installed="0.1.0", latest="0.2.0")]


def _report_body(app):
    rep = app.screen
    assert isinstance(rep, scr.RunReportScreen), type(rep).__name__
    return str(rep.query_one("#report-text", Static).renderable)


class CancelTests(unittest.TestCase):
    async def _start(self, app, pilot, rows=None):
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()

    def test_single_esc_opens_confirm(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner()
            app = make_app(d, runner=runner)

            async def go():
                async with app.run_test() as pilot:
                    await self._start(app, pilot)
                    await _wait_started(runner)
                    await pilot.press("escape")
                    await pilot.pause()
                    assert isinstance(app.screen, scr.CancelConfirmScreen), type(app.screen).__name__
                    await pilot.press("n")
                    await pilot.pause()
                    assert isinstance(app.screen, scr.MainScreen)
                    assert app.run_active, "No keeps the run going"
                    ctl0 = app._run_control
                    assert ctl0 is not None
                    assert ctl0.stop is None
                    runner.release.set()
                    await _wait_done(app)

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_yes_then_finish_current(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner()
            app = make_app(d, rows=TWO_OUTDATED, runner=runner)

            async def go():
                async with app.run_test() as pilot:
                    await self._start(app, pilot)
                    await _wait_started(runner)
                    await pilot.press("escape")
                    await pilot.pause()
                    await pilot.press("y")
                    await pilot.pause()
                    assert isinstance(app.screen, scr.CancelModeScreen)
                    await pilot.press("f")
                    await pilot.pause()
                    ctl1 = app._run_control
                    assert ctl1 is not None
                    assert ctl1.stop == "after_current"
                    assert app.run_active, "finish-current keeps the run open"
                    runner.release.set()
                    await _wait_done(app)
                    body = _report_body(app)
                    assert "skipped" in body, body

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_yes_then_immediate(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner()
            app = make_app(d, rows=TWO_OUTDATED, runner=runner)

            async def go():
                async with app.run_test() as pilot:
                    await self._start(app, pilot)
                    await _wait_started(runner)
                    await pilot.press("escape")
                    await pilot.pause()
                    await pilot.press("y")
                    await pilot.pause()
                    mode = app.screen
                    assert isinstance(mode, scr.CancelModeScreen)
                    warning = str(mode.query_one("#cancel-warning", Static).renderable)
                    assert "half-updated" in warning, warning  # B7 warning wording
                    stops = []
                    ctl = app._run_control
                    assert ctl is not None
                    orig_stop = ctl.request_stop

                    def spy(mode):
                        stops.append(mode)
                        orig_stop(mode)

                    ctl.request_stop = spy
                    await pilot.press("c")
                    await pilot.pause()
                    assert stops == ["immediate"], stops  # _run_control is cleared at finish
                    runner.release.set()
                    await _wait_done(app)
                    body = _report_body(app)
                    assert "cancelled" in body, body

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_double_escape_is_immediate(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner()
            app = make_app(d, runner=runner)

            async def go():
                async with app.run_test() as pilot:
                    await self._start(app, pilot)
                    await _wait_started(runner)
                    stops = []
                    ctl = app._run_control
                    assert ctl is not None
                    orig_stop = ctl.request_stop

                    def spy(mode):
                        stops.append(mode)
                        orig_stop(mode)

                    ctl.request_stop = spy
                    await pilot.press("escape", "escape")  # one call: lands within 0.5 s
                    await pilot.pause()
                    assert stops == ["immediate"], stops  # _run_control is cleared at finish
                    cancel_types = (scr.CancelConfirmScreen, scr.CancelModeScreen)
                    assert not any(isinstance(s, cancel_types) for s in app.screen_stack)
                    runner.release.set()
                    await _wait_done(app)
                    body = _report_body(app)
                    assert "cancelled" in body, body

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_slow_second_escape_just_dismisses(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner()
            app = make_app(d, runner=runner)

            async def go():
                async with app.run_test() as pilot:
                    await self._start(app, pilot)
                    await _wait_started(runner)
                    await pilot.press("escape")
                    await pilot.pause()
                    assert isinstance(app.screen, scr.CancelConfirmScreen)
                    await pilot.pause(0.7)  # beyond the 0.5 s double-Esc window
                    await pilot.press("escape")
                    await pilot.pause()
                    assert isinstance(app.screen, scr.MainScreen), "a later Esc just dismisses"
                    ctl2 = app._run_control
                    assert ctl2 is not None
                    assert ctl2.stop is None
                    assert app.run_active
                    runner.release.set()
                    await _wait_done(app)

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_finish_run_pops_cancel_dialog_before_report(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner()
            app = make_app(d, runner=runner)

            async def go():
                async with app.run_test() as pilot:
                    await self._start(app, pilot)
                    await _wait_started(runner)
                    await pilot.press("escape")
                    await pilot.pause()
                    assert isinstance(app.screen, scr.CancelConfirmScreen)
                    # the run finishes while the dialog is still open
                    runner.release.set()
                    await _wait_done(app)
                    assert isinstance(app.screen, scr.RunReportScreen), \
                        f"_finish_run must push the report, got {type(app.screen).__name__}"
                    cancel_types = (scr.CancelConfirmScreen, scr.CancelModeScreen)
                    assert not any(isinstance(s, cancel_types) for s in app.screen_stack), \
                        "no cancel dialog may be left under the report"

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_ctrl_q_blocked_during_run(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner()
            app = make_app(d, runner=runner)

            async def go():
                async with app.run_test() as pilot:
                    await self._start(app, pilot)
                    await _wait_started(runner)
                    await pilot.press("ctrl+q")
                    await pilot.pause()
                    assert app.is_running, "ctrl+q must not quit mid-run"
                    runner.release.set()
                    await _wait_done(app)

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_esc_outside_run_still_leaves_mode(self):
        with tempfile.TemporaryDirectory() as d:
            app = make_app(d, runner=GatedRunner())

            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("u")
                    await pilot.pause()
                    assert app.mode == "update"
                    await pilot.press("escape")
                    await pilot.pause()
                    assert app.mode is None, "existing behaviour unchanged outside a run"

            asyncio.run(asyncio.wait_for(go(), 10))


if __name__ == "__main__":
    unittest.main()
