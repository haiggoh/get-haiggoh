#!/usr/bin/env python3
"""Task 6 pilot contract: the bulk run is LIVE on the main list — worker thread,
spinner+bar on the running row, dim heartbeat line under Q) Quit (one gap row),
report modal, locks while running, background post-run refresh.

Run ONLY under the TUI venv python (0 skipped is the receipt):
  ~/.local/share/get-haiggoh/tui-venv/bin/python -m pytest tests/tui/test_live_run.py -q -rs
"""
import asyncio
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import pytest

textual = pytest.importorskip("textual")  # venv run: 0 skipped is the receipt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from rich.text import Text  # noqa: E402
from textual.widgets import Static  # noqa: E402

from get_haiggoh_tui import runner as rn  # noqa: E402
from get_haiggoh_tui import screens as scr  # noqa: E402
from get_haiggoh_tui.runstate import SPINNER, cell_width  # noqa: E402
from tests.tui.live_rig import GatedRunner  # noqa: E402
from tests.tui.test_app_pilot import make_app, make_rows, row  # noqa: E402


async def _wait_started(runner, timeout=5.0):
    t0 = time.monotonic()
    while not runner.started.is_set():
        if time.monotonic() - t0 > timeout:
            raise AssertionError("runner never started")
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.15)  # let the queued start event + a tick land


async def _wait_done(app, timeout=5.0):
    t0 = time.monotonic()
    while app.run_active:
        if time.monotonic() - t0 > timeout:
            raise AssertionError("run never finished")
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.1)


def _ids(ol):
    return [o.id for o in ol.options]


def _prompt(ol, oid):
    return ol.get_option_at_index(_ids(ol).index(oid)).prompt.plain


class LiveRunTests(unittest.TestCase):
    async def _start_update(self, app, pilot):
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()
        await pilot.press("u")  # same key again runs the mode
        await pilot.pause()

    def test_run_does_not_block_ui(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner()
            app = make_app(d, runner=runner)

            async def go():
                async with app.run_test() as pilot:
                    await self._start_update(app, pilot)
                    await _wait_started(runner)
                    ol = app.screen.query_one("#rows")
                    before = ol.highlighted
                    await pilot.press("down")
                    await pilot.pause()
                    assert ol.highlighted != before, "arrows still move during the run"
                    assert isinstance(app.screen, scr.MainScreen), "no modal lockout"
                    assert app.run_active
                    runner.release.set()
                    await _wait_done(app)
                    assert not app.run_active
                    assert isinstance(app.screen, scr.RunReportScreen)

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_running_row_has_spinner_and_bar(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner()
            app = make_app(d, runner=runner)

            async def go():
                async with app.run_test() as pilot:
                    await self._start_update(app, pilot)
                    await _wait_started(runner)
                    ol = app.screen.query_one("#rows")
                    prompt = _prompt(ol, "waypoints")
                    assert any(ch in SPINNER for ch in prompt), prompt
                    assert "▐" in prompt, prompt
                    assert prompt.index("▐") > prompt.index("waypoints"), \
                        "spinner+bar sit right after the name"
                    runner.release.set()
                    await _wait_done(app)

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_dim_line_below_quit_after_gap(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner()
            app = make_app(d, runner=runner)

            async def go():
                async with app.run_test() as pilot:
                    await self._start_update(app, pilot)
                    await _wait_started(runner)
                    ol = app.screen.query_one("#rows")
                    ids = _ids(ol)
                    assert ids[-3:] == ["action:quit", "gap:runstatus", "runstatus"], ids[-3:]
                    opt = ol.get_option_at_index(ids.index("runstatus"))
                    assert opt.disabled, "the dim line is a disabled (grey) option"
                    assert opt.prompt.plain.startswith("▸ resolving…"), opt.prompt.plain
                    runner.release.set()
                    await _wait_done(app)
                    await pilot.press("escape")  # dismiss the report
                    await pilot.pause()
                    ids2 = _ids(app.screen.query_one("#rows"))
                    assert "runstatus" not in ids2 and "gap:runstatus" not in ids2

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_heartbeat_changes_without_output(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner(lines=())
            app = make_app(d, runner=runner)

            async def go():
                async with app.run_test() as pilot:
                    await self._start_update(app, pilot)
                    await _wait_started(runner)
                    ol = app.screen.query_one("#rows")
                    s0 = _prompt(ol, "runstatus")
                    await pilot.pause(0.5)  # let the 150 ms tick fire a few times
                    s1 = _prompt(ol, "runstatus")
                    assert s0 != s1, "the heartbeat must change even with zero output"
                    runner.release.set()
                    await _wait_done(app)

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_row_flips_when_step_finishes(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner(gate_after_result=True)
            app = make_app(d, runner=runner)

            async def go():
                async with app.run_test() as pilot:
                    await self._start_update(app, pilot)
                    await _wait_started(runner)
                    runner.release.set()
                    # while the run is still open (runner blocked after the result),
                    # the row already shows the finished decoration
                    ol = app.screen.query_one("#rows")
                    t0 = time.monotonic()
                    while "✓ 9.9" not in _prompt(ol, "waypoints"):
                        if time.monotonic() - t0 > 3:
                            raise AssertionError("row never flipped to ✓ 9.9")
                        await asyncio.sleep(0.02)
                    assert app.run_active, "the flip must be observed WHILE the run is still open"
                    runner.after_result.set()
                    await _wait_done(app)
                    await pilot.press("escape")
                    await pilot.pause()
                    assert "9.9" in _prompt(app.screen.query_one("#rows"), "waypoints")
                    # (app.rows replacement is pinned by test_list_reflects_after_rows_immediately
                    #  with a slow loader — here the fast background refresh may race it)

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_report_lists_results(self):
        with tempfile.TemporaryDirectory() as d:
            rows = [row("waypoints", "outdated", installed="0.14.3", latest="0.15.0"),
                    row("cost-tracker", "outdated", installed="0.1.0", latest="0.2.0")]
            runner = GatedRunner(outcome={"waypoints": "ok", "cost-tracker": "failed"},
                                 result_output="brew: command not found\nmore")
            app = make_app(d, rows=rows, runner=runner)

            async def go():
                async with app.run_test() as pilot:
                    await self._start_update(app, pilot)
                    await _wait_started(runner)
                    runner.release.set()
                    await _wait_done(app)
                    rep = app.screen
                    assert isinstance(rep, scr.RunReportScreen), type(rep).__name__
                    title = str(rep.query_one("#report-title", Static).renderable)
                    body = str(rep.query_one("#report-text", Static).renderable)
                    assert "1 ok · 1 failed" in title, title
                    assert "✓ waypoints (plugin)" in body, body
                    assert "brew: command not found" in body, body
                    assert "more" not in body, "only the first error line is shown"

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_report_escapes_bracket_markup(self):
        # the 0.10.2 bug class: "[x]" as a markup string is eaten — the report body
        # must be a Text, never a raw markup-parsed string
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner(outcome="failed", result_output="error: unknown option [--foo]")
            app = make_app(d, runner=runner)

            async def go():
                async with app.run_test() as pilot:
                    await self._start_update(app, pilot)
                    await _wait_started(runner)
                    runner.release.set()
                    await _wait_done(app)
                    rep = app.screen
                    assert isinstance(rep, scr.RunReportScreen)
                    static = rep.query_one("#report-text", Static)
                    assert isinstance(static.renderable, Text), \
                        f"report body must be a Text, got {type(static.renderable).__name__}"
                    assert "[--foo]" in static.renderable.plain, static.renderable.plain

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_report_is_a_small_overlay_with_menu_visible_behind(self):
        # dogfood feedback 2026-11-25: the full-screen report looked like the menu
        # disappeared / the install was interrupted. The report must be a small
        # centered box with the live menu still rendered behind it.
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner()
            app = make_app(d, runner=runner)
            shot = Path(d) / "report.svg"

            async def go():
                async with app.run_test(size=(100, 40)) as pilot:
                    await self._start_update(app, pilot)
                    await _wait_started(runner)
                    runner.release.set()
                    await _wait_done(app)
                    rep = app.screen
                    assert isinstance(rep, scr.RunReportScreen), type(rep).__name__
                    box = rep.query_one("#report-box")  # raises if there is no box
                    await pilot.pause(0.3)  # let layout settle
                    assert box.region.width < rep.size.width, \
                        f"report box must be narrower than the screen: {box.region}"
                    assert box.region.height < rep.size.height, \
                        f"report box must be shorter than the screen: {box.region}"
                    app.save_screenshot(str(shot))
                    # Rich's SVG export encodes spaces as &#160; — decode before matching
                    svg = shot.read_text(encoding="utf-8").replace("&#160;", " ")
                    assert "Update report" in svg, "report not rendered"
                    assert "Q) Quit" in svg, "the menu must still be rendered BEHIND the report"
                    await pilot.press("escape")  # dismiss still works
                    await pilot.pause()
                    assert isinstance(app.screen, scr.MainScreen)

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_q_does_not_quit_during_run(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner()
            app = make_app(d, runner=runner)
            notified = []
            orig_notify = app.notify
            app.notify = lambda msg, *a, **kw: (notified.append(str(msg)),
                                                orig_notify(msg, *a, **kw))[1]

            async def go():
                async with app.run_test() as pilot:
                    await self._start_update(app, pilot)
                    await _wait_started(runner)
                    await pilot.press("q")
                    await pilot.pause()
                    assert app.is_running, "q must not quit mid-run"
                    assert any("esc to cancel" in m for m in notified), notified
                    runner.release.set()
                    await _wait_done(app)

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_ticks_and_modes_inert_during_run(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner()
            app = make_app(d, runner=runner)

            async def go():
                async with app.run_test() as pilot:
                    await self._start_update(app, pilot)
                    await _wait_started(runner)
                    ticks_before = set(app.ticks)
                    await pilot.press("space", "a", "u", "i", "x")
                    await pilot.pause()
                    assert app.mode is None, "mode keys are inert during a run"
                    assert app.ticks == ticks_before, "tick keys are inert during a run"
                    assert len(runner.calls) == 1, "no second run was started"
                    runner.release.set()
                    await _wait_done(app)

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_refresh_mid_run_keeps_decorations(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner()
            app = make_app(d, runner=runner)

            async def go():
                async with app.run_test() as pilot:
                    await self._start_update(app, pilot)
                    await _wait_started(runner)
                    app._apply_rows(make_rows())  # the background refresh landing mid-run
                    await pilot.pause()
                    prompt = _prompt(app.screen.query_one("#rows"), "waypoints")
                    assert any(ch in SPINNER for ch in prompt) and "▐" in prompt, prompt
                    runner.release.set()
                    await _wait_done(app)

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_runner_crash_unlocks_and_reports(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner(raise_exc=RuntimeError("boom"))
            app = make_app(d, runner=runner)

            async def go():
                async with app.run_test() as pilot:
                    await self._start_update(app, pilot)
                    await _wait_started(runner)
                    runner.release.set()
                    await _wait_done(app)
                    assert not app.run_active
                    rep = app.screen
                    assert isinstance(rep, scr.RunReportScreen)
                    body = str(rep.query_one("#report-text", Static).renderable)
                    assert "run crashed: boom" in body, body

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_flood_of_output_keeps_ui_responsive(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner(lines=[f"l{i}" for i in range(5000)])
            app = make_app(d, runner=runner)

            async def go():
                async with app.run_test() as pilot:
                    await self._start_update(app, pilot)
                    await _wait_started(runner)
                    ol = app.screen.query_one("#rows")
                    before = ol.highlighted
                    await pilot.press("down")
                    await pilot.pause()
                    assert ol.highlighted != before, "the UI answers keys during a 5000-line flood"
                    await pilot.pause(0.3)  # let a tick paint the last line
                    assert "l4999" in _prompt(ol, "runstatus"), _prompt(ol, "runstatus")
                    runner.release.set()
                    await _wait_done(app)

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_dim_line_single_line_in_narrow_terminal(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner()
            app = make_app(d, runner=runner)

            async def go():
                async with app.run_test(size=(50, 40)) as pilot:
                    await self._start_update(app, pilot)
                    await _wait_started(runner)
                    ol = app.screen.query_one("#rows")
                    width = ol.scrollable_content_region.width
                    prompt = _prompt(ol, "runstatus")
                    assert cell_width(prompt) <= width, (prompt, width)
                    runner.release.set()
                    await _wait_done(app)

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_runner_gets_local_reread(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner()
            sentinel = lambda b: b  # noqa: E731
            app = make_app(d, runner=runner, reread_one=sentinel)

            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("u")
                    await pilot.pause()
                    names_before = [r.name for r in app.rows]
                    await pilot.press("u")
                    await _wait_started(runner)
                    kw = runner.kwargs[-1]
                    assert kw["reread_one"] is sentinel
                    assert [r.name for r in kw["rows"]] == names_before
                    runner.release.set()
                    await _wait_done(app)

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_report_appears_without_full_refresh_on_ui_thread(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner()
            counter = {"n": 0}
            lock = threading.Lock()

            def loader(cached):
                if not cached:
                    with lock:
                        counter["n"] += 1
                    time.sleep(3)  # the full sweep — must run in the background
                return make_rows()

            app = make_app(d, runner=runner, rows_loader=loader)

            async def go():
                async with app.run_test() as pilot:
                    await self._start_update(app, pilot)
                    await _wait_started(runner)
                    runner.release.set()
                    t0 = time.monotonic()
                    while not isinstance(app.screen, scr.RunReportScreen):
                        if time.monotonic() - t0 > 2:
                            raise AssertionError("report did not appear promptly")
                        await asyncio.sleep(0.02)
                    assert time.monotonic() - t0 < 1.0, \
                        "the report must not wait for the 3 s full refresh"
                    await _wait_done(app)
                    t1 = time.monotonic()
                    while counter["n"] < 1 and time.monotonic() - t1 < 5:
                        await asyncio.sleep(0.05)
                    assert counter["n"] >= 1, "the slow loader runs in the background worker"

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_list_reflects_after_rows_immediately(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner()  # after_row installed="9.9"

            def loader(cached):
                if not cached:
                    time.sleep(3)
                return make_rows()

            app = make_app(d, runner=runner, rows_loader=loader)

            async def go():
                async with app.run_test() as pilot:
                    await self._start_update(app, pilot)
                    await _wait_started(runner)
                    runner.release.set()
                    await _wait_done(app)
                    r = next(r for r in app.rows if r.name == "waypoints")
                    assert r.installed == "9.9", "after_row applied before any refresh lands"

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_self_update_runs_inline_then_relaunches(self):
        with tempfile.TemporaryDirectory() as d:
            rows = [row("get-haiggoh", "outdated", installed="0.9.4", latest="0.10.0",
                        mark="👨🏻‍💻"),
                    row("waypoints", "outdated", installed="0.14.3", latest="0.15.0")]
            runner = GatedRunner()
            execs = []
            app = make_app(d, rows=rows, runner=runner,
                           execv=lambda p, a: execs.append((p, list(a))))

            async def go():
                async with app.run_test() as pilot:
                    await self._start_update(app, pilot)
                    await _wait_started(runner)
                    assert isinstance(app.screen, scr.MainScreen), "self-update runs inline"
                    ol = app.screen.query_one("#rows")
                    before = ol.highlighted
                    await pilot.press("down")
                    await pilot.pause()
                    assert ol.highlighted != before, "arrows work during the self-update"
                    runner.release.set()
                    await _wait_done(app)
                    assert not isinstance(app.screen, scr.RunReportScreen), \
                        "a successful self-update relaunches instead of reporting"

            asyncio.run(asyncio.wait_for(go(), 10))
            data = rn.read_pending(app.pending_path)
            assert data is not None and data["names"] == ["waypoints"], data
            assert execs and "--resume" in execs[0][1], execs

    def test_failed_self_update_continues_inline(self):
        with tempfile.TemporaryDirectory() as d:
            rows = [row("get-haiggoh", "outdated", installed="0.9.4", latest="0.10.0",
                        mark="👨🏻‍💻"),
                    row("waypoints", "outdated", installed="0.14.3", latest="0.15.0")]
            runner = GatedRunner(outcome="failed")
            execs = []
            app = make_app(d, rows=rows, runner=runner,
                           execv=lambda p, a: execs.append((p, list(a))))

            async def go():
                async with app.run_test() as pilot:
                    await self._start_update(app, pilot)
                    await _wait_started(runner)
                    runner.release.set()
                    await _wait_done(app, timeout=8)
                    rep = app.screen
                    assert isinstance(rep, scr.RunReportScreen)
                    body = str(rep.query_one("#report-text", Static).renderable)
                    assert "get-haiggoh" in body and "waypoints" in body, \
                        "the report lists both runs' results"

            asyncio.run(asyncio.wait_for(go(), 10))
            assert execs == [], "a failed self-update must NOT relaunch"
            assert runner.calls == [["get-haiggoh"], ["waypoints"]], runner.calls

    def test_running_row_scrolled_into_view(self):
        with tempfile.TemporaryDirectory() as d:
            rows = [row(f"plug-{i:02d}", "missing") for i in range(25)]
            rows.append(row("waypoints", "outdated", installed="0.14.3", latest="0.15.0"))
            runner = GatedRunner()
            app = make_app(d, rows=rows, runner=runner)

            async def go():
                async with app.run_test(size=(80, 20)) as pilot:
                    await pilot.pause()
                    await pilot.press("u")
                    await pilot.pause()
                    ol = app.screen.query_one("#rows")
                    enabled = [i for i, o in enumerate(ol.options) if not o.disabled]
                    ol.highlighted = enabled[0]
                    hl_before = ol.highlighted
                    await pilot.press("u")
                    await _wait_started(runner)
                    await pilot.pause(0.3)
                    ids = _ids(ol)
                    idx = ids.index("waypoints")
                    # ol._lines is private; its POSITION is the content line (pinned here)
                    y = next(pos for pos, (i, _o) in enumerate(ol._lines) if i == idx)
                    region = ol.scrollable_content_region
                    top = ol.scroll_offset.y
                    assert top <= y < top + region.height, \
                        f"running row not visible: y={y} top={top} region={region}"
                    assert ol.highlighted == hl_before, "scrolling must not move the highlight"
                    runner.release.set()
                    await _wait_done(app)

            asyncio.run(asyncio.wait_for(go(), 10))

    def test_invalid_timeout_refuses_to_run(self):
        with tempfile.TemporaryDirectory() as d:
            runner = GatedRunner()
            app = make_app(d, runner=runner)
            notified = []
            orig_notify = app.notify
            app.notify = lambda msg, *a, **kw: (notified.append(str(msg)),
                                                orig_notify(msg, *a, **kw))[1]

            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    await pilot.press("u")
                    await pilot.pause()
                    with mock.patch.dict(os.environ, {"GET_HAIGGOH_STEP_TIMEOUT": "abc"}):
                        await pilot.press("u")
                        await pilot.pause()
                        await asyncio.sleep(0.2)
                    assert runner.calls == [], "an invalid timeout refuses to start the run"
                    assert any("GET_HAIGGOH_STEP_TIMEOUT" in m for m in notified), notified
                    assert not app.run_active

            asyncio.run(asyncio.wait_for(go(), 10))


if __name__ == "__main__":
    unittest.main()
