#!/usr/bin/env python3
"""0.10.2 contract (user 2026-11-09): stray `p`, ⏳ loading frame, menu links that resolve,
browse/select modes, grouped rows, non-link hover, rounded info box near the buttons.

Run with the TUI venv python so a skip cannot read green:
  ~/.local/share/get-haiggoh/tui-venv/bin/python -m pytest tests/tui/test_tui_0102.py -rs -q
"""
import asyncio
import os
import pty
import select
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import pytest

textual = pytest.importorskip("textual")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from get_haiggoh_tui import app as app_mod  # noqa: E402
from get_haiggoh_tui import menuspec as ms  # noqa: E402
from test_app_pilot import make_app, make_rows, row  # noqa: E402

MENU = {"argv": ["tool-cli"], "spec_min_version": None, "return_to_min_version": None}


def run(coro):
    return asyncio.run(coro)


def rendered(ol):
    """What Textual actually draws per option (markup applied), by option id."""
    return {o.id: ol._get_visual(o).plain for o in ol.options}


# --- 1. stray `p`: the Apple Terminal driver -----------------------------------------

class DriverTests(unittest.TestCase):
    def test_apple_terminal_gets_safe_driver_and_no_2048_query(self):
        with mock.patch.dict(os.environ, {"TERM_PROGRAM": "Apple_Terminal"}):
            cls = app_mod.get_driver_class()
            with tempfile.TemporaryDirectory() as d:
                inst = make_app(d)
            self.assertIs(inst.driver_class, cls)
            self.assertTrue(issubclass(cls, app_mod.AppleTerminalSafeDriver))
            written = []
            drv = cls.__new__(cls)
            drv.write = written.append
            drv._query_in_band_window_resize()
            self.assertEqual(written, [], "Apple Terminal must not get ?2048$p")

    def test_other_terminals_keep_the_query(self):
        with mock.patch.dict(os.environ, {"TERM_PROGRAM": "iTerm.app"}):
            cls = app_mod.get_driver_class()
            written = []
            drv = cls.__new__(cls)
            drv.write = written.append
            drv._query_in_band_window_resize()
            self.assertEqual(written, ["\x1b[?2048$p"])


# --- 2. ⏳ loading frame from the launcher, before anything else ---------------------

def _fake_venv(d):
    """A venv whose python is a stub, with a matching .req-sha, so the launcher execs it."""
    import hashlib
    venv = Path(d) / "venv"
    (venv / "bin").mkdir(parents=True)
    py = venv / "bin" / "python"
    py.write_text("#!/bin/sh\necho STUB-TUI\n")
    py.chmod(py.stat().st_mode | stat.S_IXUSR)
    sha = hashlib.sha256((ROOT / "tui-requirements.txt").read_bytes()).hexdigest()
    (venv / ".req-sha").write_text(sha + "\n")
    return venv


def _pty_run(argv, env, timeout=10):
    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe(argv[0], argv, env)
    out, end = b"", time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
    os.waitpid(pid, 0)
    return out


class LoadingFrameTests(unittest.TestCase):
    def test_first_bytes_on_a_tty_are_the_loading_frame(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, GET_HAIGGOH_TUI_VENV=str(_fake_venv(d)))
            out = _pty_run([sys.executable, str(ROOT / "bin" / "get-haiggoh-tui")], env)
            text = out.decode("utf-8", "replace")
            self.assertTrue(text.startswith("\x1b[?1049h"), repr(text[:40]))
            self.assertIn("⏳ loading ...", text)
            self.assertLess(text.index("⏳ loading ..."), text.index("STUB-TUI"))

    def test_pipe_gets_no_escape_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, GET_HAIGGOH_TUI_VENV=str(_fake_venv(d)))
            r = subprocess.run([sys.executable, str(ROOT / "bin" / "get-haiggoh-tui")],
                               env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(r.stdout, "STUB-TUI\n")


# --- 3. menu links resolve outside Claude's PATH ------------------------------------

class ResolveTests(unittest.TestCase):
    def _plugin(self, d, rel, executable):
        root = Path(d) / "cache" / "tool" / "1.0"
        p = root / rel
        p.parent.mkdir(parents=True)
        p.write_text("#!/usr/bin/env python3\n")
        if executable:
            p.chmod(p.stat().st_mode | stat.S_IXUSR)
        return root, p

    def test_plugin_bin_script_not_executable_runs_via_python3(self):
        with tempfile.TemporaryDirectory() as d:
            root, p = self._plugin(d, "bin/tool-cli.py", executable=False)
            r = row("tool", "current", menu={**MENU, "argv": ["tool-cli.py", "setup"]})
            kind, payload = ms.menu_for(r, installed={"tool": {"installPath": str(root)}},
                                        which=lambda n: "/usr/bin/python3" if n == "python3" else None)
            self.assertEqual((kind, payload), ("legacy", ["/usr/bin/python3", str(p), "setup"]))

    def test_plugin_root_script_executable_runs_directly(self):
        with tempfile.TemporaryDirectory() as d:
            root, p = self._plugin(d, "tool_menu.py", executable=True)
            r = row("tool", "current", menu={**MENU, "argv": ["tool_menu.py"]})
            kind, payload = ms.menu_for(r, installed={"tool": {"installPath": str(root)}},
                                        which=lambda n: None)
            self.assertEqual((kind, payload), ("legacy", [str(p)]))

    def test_on_path_wins(self):
        r = row("tool", "current", menu=MENU)
        kind, payload = ms.menu_for(r, installed={}, which=lambda n: "/x/bin/" + n)
        self.assertEqual((kind, payload), ("legacy", ["/x/bin/tool-cli"]))

    def test_unresolvable_is_missing_not_a_crash(self):
        r = row("tool", "current", menu=MENU)
        kind, payload = ms.menu_for(r, installed={}, which=lambda n: None)
        self.assertEqual(kind, "missing")
        self.assertIn("tool-cli", payload)

    def test_catalog_has_no_cwd_relative_argv(self):
        import json
        for f in ("plugin-extras.json", "related-tools.json"):
            data = json.loads((ROOT / "catalog" / f).read_text())
            items = data.values() if isinstance(data, dict) else data
            for it in items:
                m = isinstance(it, dict) and it.get("menu")
                if m:
                    self.assertFalse(m["argv"][0].startswith("./"), (f, m))

    def test_enter_on_missing_exe_notifies_and_stays_alive(self):
        with tempfile.TemporaryDirectory() as d:
            notes = []
            app = make_app(d, menu_for=lambda r: ("missing", "tool-cli not found")
                           if r.name == "mac-claude-migration" else ("none", None))
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    app.notify = lambda msg, **kw: notes.append(msg)
                    ol = app.screen.query_one("#rows")
                    ol.highlighted = next(i for i, o in enumerate(ol.options)
                                          if o.id == "mac-claude-migration")
                    await pilot.press("enter")
                    await pilot.pause()
                    return type(app.screen).__name__
            self.assertEqual(run(go()), "MainScreen")
            self.assertTrue(any("tool-cli not found" in n for n in notes), notes)

    def test_oserror_from_runner_notifies_not_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            notes = []
            def boom(argv):
                raise FileNotFoundError(2, "No such file or directory", argv[0])
            app = make_app(d, legacy_runner=boom,
                           menu_for=lambda r: ("legacy", ["nope"]) if r.name == "mac-claude-migration" else ("none", None),
                           suspend_fn=lambda: _NullSuspend())
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    app.notify = lambda msg, **kw: notes.append(msg)
                    ol = app.screen.query_one("#rows")
                    ol.highlighted = next(i for i, o in enumerate(ol.options)
                                          if o.id == "mac-claude-migration")
                    await pilot.press("enter")
                    await pilot.pause()
                    return type(app.screen).__name__
            self.assertEqual(run(go()), "MainScreen")
            self.assertTrue(any("nope" in n for n in notes), notes)


class _NullSuspend:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# --- 4. browse mode / select mode ---------------------------------------------------

def menu_rows():
    rows = make_rows()
    for r in rows:
        if r.name in ("waypoints", "free-agents"):
            r.menu = MENU
    return rows


class ModeTests(unittest.TestCase):
    def _go(self, d, script, rows=None):
        app = make_app(d, rows=rows or menu_rows())
        async def go():
            async with app.run_test() as pilot:
                await pilot.pause()
                return await script(app, pilot)
        return app, run(go())

    def test_browse_mode_has_no_checkboxes(self):
        with tempfile.TemporaryDirectory() as d:
            async def s(app, pilot):
                return rendered(app.screen.query_one("#rows"))
            _app, labels = self._go(d, s)
            for oid, text in labels.items():
                if oid and not oid.startswith(("section:", "gap:")):
                    self.assertFalse(text.startswith("["), (oid, text))

    def test_browse_groups_menu_rows_first_with_a_gap(self):
        with tempfile.TemporaryDirectory() as d:
            async def s(app, pilot):
                return [o.id for o in app.screen.query_one("#rows").options]
            _app, ids = self._go(d, s)
            plugin = ids[ids.index("section:plugin") + 1: ids.index("section:tool")]
            self.assertEqual(plugin[:2], ["waypoints", "free-agents"])
            self.assertEqual(plugin[2], "gap:plugin")
            self.assertEqual(set(plugin[3:]), {"get-haiggoh", "cost-tracker"})

    def test_space_does_nothing_in_browse_mode(self):
        with tempfile.TemporaryDirectory() as d:
            async def s(app, pilot):
                app.ticks = set()
                ol = app.screen.query_one("#rows")
                ol.highlighted = next(i for i, o in enumerate(ol.options) if o.id == "waypoints")
                await pilot.press("space")
                await pilot.pause()
                return set(app.ticks)
            _app, ticks = self._go(d, s)
            self.assertEqual(ticks, set())

    def test_update_mode_ticks_eligible_and_shows_x(self):
        with tempfile.TemporaryDirectory() as d:
            async def s(app, pilot):
                await pilot.press("u")
                await pilot.pause()
                ol = app.screen.query_one("#rows")
                return app.mode, set(app.ticks), rendered(ol), {o.id: o.disabled for o in ol.options}
            _app, (mode, ticks, labels, disabled) = self._go(d, s)
            self.assertEqual(mode, "update")
            self.assertEqual(ticks, {"waypoints"})
            self.assertTrue(labels["waypoints"].startswith("[x] "), labels["waypoints"])
            self.assertFalse(disabled["waypoints"])
            # ineligible rows stay listed, greyed (disabled), with no box
            self.assertTrue(disabled["free-agents"])
            self.assertFalse(labels["free-agents"].lstrip().startswith("["))

    def test_select_all_puts_x_in_every_eligible_box(self):
        with tempfile.TemporaryDirectory() as d:
            async def s(app, pilot):
                await pilot.press("i")
                await pilot.press("n")
                await pilot.press("a")
                await pilot.pause()
                return set(app.ticks), rendered(app.screen.query_one("#rows"))
            _app, (ticks, labels) = self._go(d, s)
            self.assertEqual(ticks, {"cost-tracker", "human-shell"})
            for name in ticks:
                self.assertTrue(labels[name].startswith("[x] "), labels[name])

    def test_uninstall_mode_starts_unticked(self):
        with tempfile.TemporaryDirectory() as d:
            async def s(app, pilot):
                await pilot.press("x")
                await pilot.pause()
                return app.mode, set(app.ticks), rendered(app.screen.query_one("#rows"))
            _app, (mode, ticks, labels) = self._go(d, s)
            self.assertEqual((mode, ticks), ("uninstall", set()))
            self.assertTrue(labels["waypoints"].startswith("[ ] "))

    def test_escape_and_b_leave_mode(self):
        for key in ("escape", "b"):
            with tempfile.TemporaryDirectory() as d:
                async def s(app, pilot, key=key):
                    await pilot.press("u")
                    await pilot.press(key)
                    await pilot.pause()
                    return app.mode, rendered(app.screen.query_one("#rows"))
                _app, (mode, labels) = self._go(d, s)
                self.assertIsNone(mode, key)
                self.assertFalse(labels["waypoints"].startswith("["), key)

    def test_same_key_again_runs(self):
        with tempfile.TemporaryDirectory() as d:
            async def s(app, pilot):
                await pilot.press("u")
                await pilot.pause()
                assert app.runner.calls == [], "first u only enters the mode"
                await pilot.press("u")
                await pilot.pause()
                return app.runner.calls
            _app, calls = self._go(d, s)
            self.assertEqual(calls, [["waypoints"]])

    def test_enter_runs_in_mode(self):
        with tempfile.TemporaryDirectory() as d:
            async def s(app, pilot):
                await pilot.press("i")
                await pilot.pause()
                assert app.runner.calls == [], "i only enters the mode"
                await pilot.press("enter")
                await pilot.pause()
                return app.runner.calls
            _app, calls = self._go(d, s)
            self.assertEqual(len(calls), 1)
            self.assertEqual(set(calls[0]), {"cost-tracker", "human-shell"})

    def test_enter_on_no_menu_row_does_nothing_in_browse(self):
        with tempfile.TemporaryDirectory() as d:
            opened = []
            app = make_app(d, rows=menu_rows(),
                           menu_for=lambda r: (opened.append(r.name), ("none", None))[1])
            async def go():
                async with app.run_test() as pilot:
                    await pilot.pause()
                    ol = app.screen.query_one("#rows")
                    ol.highlighted = next(i for i, o in enumerate(ol.options) if o.id == "cost-tracker")
                    await pilot.press("enter")
                    await pilot.pause()
                    return app.focused.id if app.focused else None
            focused = run(go())
            self.assertEqual(opened, [])
            self.assertEqual(focused, "rows", "a non-link row must not move focus")

    def test_non_link_row_hover_uses_non_link_style(self):
        with tempfile.TemporaryDirectory() as d:
            async def s(app, pilot):
                ol = app.screen.query_one("#rows")
                return ol.nonlink_ids, "option-list--option-nonlink" in type(ol).COMPONENT_CLASSES
            _app, (ids, has_class) = self._go(d, s)
            self.assertTrue(has_class)
            self.assertIn("cost-tracker", ids)
            self.assertNotIn("waypoints", ids)


class KeyboardNavTests(unittest.TestCase):
    def test_arrows_move_through_rows_from_start_and_after_a_button(self):
        with tempfile.TemporaryDirectory() as d:
            app = make_app(d, rows=menu_rows())
            async def go():
                async with app.run_test(size=(100, 40)) as pilot:
                    await pilot.pause()
                    ol = app.screen.query_one("#rows")
                    ids = []
                    for _ in range(2):
                        await pilot.press("down")
                        ids.append(ol.options[ol.highlighted].id)
                    await pilot.press("up")
                    ids.append(ol.options[ol.highlighted].id)
                    app.screen.query_one("#btn-update").focus()
                    await pilot.pause()
                    await pilot.press("down")
                    ids.append(ol.options[ol.highlighted].id)
                    return ids
            ids = run(go())
            real = [i for i in ids if not i.startswith(("section:", "gap:"))]
            self.assertEqual(real, ids, "arrows never stop on a header or gap")
            self.assertEqual(ids[0], ids[2])
            self.assertNotEqual(ids[0], ids[1])
            self.assertEqual(ids[3], ids[1], "arrows still drive the list after a button click")


# --- 5. info box: CSL's rounded frame, just above the buttons -----------------------

class InfoBoxTests(unittest.TestCase):
    def test_info_box_rounded_and_directly_above_buttons(self):
        with tempfile.TemporaryDirectory() as d:
            app = make_app(d)
            async def go():
                async with app.run_test(size=(100, 40)) as pilot:
                    await pilot.pause()
                    app.show_info_for("waypoints")
                    await pilot.pause()
                    info = app.screen.query_one("#info")
                    buttons = app.screen.query_one("#buttons")
                    return (info.styles.border_top[0], info.region.bottom, buttons.region.y)
            edge, info_bottom, buttons_top = run(go())
            self.assertEqual(edge, "round")
            self.assertEqual(info_bottom, buttons_top, "info box must sit right on the buttons")


if __name__ == "__main__":
    unittest.main()
