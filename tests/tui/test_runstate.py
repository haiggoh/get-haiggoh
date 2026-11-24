#!/usr/bin/env python3
"""Live-run Task 5 contract: runstate.py is PURE (no Textual, no rich) — the run
model and every string the UI paints: spinner frames by locale, bar, clamp,
elapsed, row decorations, dim line, subtitle, thread-safe note_output.

Runs under the plain pipx pytest too (no textual import).

Usage: pytest tests/tui/test_runstate.py -q
"""
import shlex
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from get_haiggoh_tui import runstate as rs  # noqa: E402
from get_haiggoh_tui import runner as rn  # noqa: E402
from get_haiggoh_tui.inventory import Row  # noqa: E402
from get_haiggoh_tui.routes import Step  # noqa: E402


def row(name, status="outdated", installed="0.8.0", latest="0.9.1"):
    return Row(name=name, section="plugin", mark="💸", description="d", adds="a",
               installed=installed, latest=latest, status=status, diagnostic=None,
               menu=None, tool=None)


def step(name, op="update", route="plugin", argv=None, note=None):
    return Step(name=name, op=op, route=route,
                argv=argv if argv is not None else ["claude", "plugin", op, f"{name}@haiggoh"],
                needs_brew=False, note=note)


class SpinnerBarClampTests(unittest.TestCase):
    def test_spinner_frames_locale(self):
        self.assertEqual(rs.spinner_frames({}), rs.SPINNER)
        self.assertEqual(rs.spinner_frames({"LC_ALL": "C"}), rs.ASCII_SPINNER)
        self.assertEqual(rs.spinner_frames({"LANG": "POSIX"}), rs.ASCII_SPINNER)
        self.assertEqual(rs.spinner_frames({"LC_ALL": "C.UTF-8"}), rs.SPINNER)
        self.assertEqual(rs.spinner_frames({"LC_ALL": "", "LANG": "C"}), rs.ASCII_SPINNER)

    def test_bar(self):
        self.assertEqual(rs.bar(0, 2), "▐░░░░░░░░░░")
        self.assertEqual(rs.bar(1, 2), "▐█████░░░░░")
        self.assertEqual(rs.bar(2, 2), "▐██████████")
        self.assertEqual(rs.bar(0, 0), "▐░░░░░░░░░░")

    def test_fmt_elapsed(self):
        self.assertEqual(rs.fmt_elapsed(14), "0:14")
        self.assertEqual(rs.fmt_elapsed(75.9), "1:15")
        self.assertEqual(rs.fmt_elapsed(3725), "1:02:05")

    def test_cell_width_and_clamp(self):
        self.assertEqual(rs.cell_width("abc"), 3)
        self.assertEqual(rs.cell_width("🧭"), 2)      # W/F => 2
        self.assertEqual(rs.cell_width("́"), 0)        # Mn => 0
        self.assertEqual(rs.clamp("hello", 10), "hello")
        cut = rs.clamp("abcdefghij", 5)
        self.assertTrue(cut.endswith("…"))
        self.assertLessEqual(rs.cell_width(cut), 5)


class RunStateTests(unittest.TestCase):
    def test_running_row_decoration(self):
        st = rs.RunState(op="update", steps=[step("waypoints", "update")], started=1000.0)
        st.on_start(st.steps[0], 1000.0)
        deco = st.row_decoration(row("waypoints", "outdated", "0.8.0", "0.9.1"),
                                 frame=0, now=1000.0, frames=rs.SPINNER)
        self.assertEqual(deco, "⠋ ▐░░░░░░░░░░ 0.8.0 → 0.9.1")

    def test_two_step_item_bar_advances(self):
        steps = [step("free-agents", "update", route="plugin"),
                 step("free-agents", "update", route="brew", argv=["brew", "upgrade", "x"])]
        st = rs.RunState(op="update", steps=steps, started=1000.0)
        st.on_start(steps[0], 1000.0)
        st.on_result(rn.StepResult(steps[0], True, "ok"))
        st.on_start(steps[1], 1001.0)
        deco = st.row_decoration(row("free-agents", "outdated", "0.1", "0.2"),
                                 0, 1001.0, rs.SPINNER)
        self.assertIn("▐█████░░░░░", deco)

    def test_finished_decorations(self):
        def deco_for(res, op="update", installed="0.8.0", latest="0.9.1"):
            st = rs.RunState(op=op, steps=[step("waypoints", op)], started=1000.0)
            st.on_start(st.steps[0], 1000.0)
            st.on_result(res)
            return st.row_decoration(row("waypoints", "outdated", installed, latest),
                                     0, 1001.0, rs.SPINNER)

        s = step("waypoints", "update")
        ok = rn.StepResult(s, True, "ok", after_row=row("waypoints", "current", "0.9.1", "0.9.1"))
        self.assertEqual(deco_for(ok), "✓ 0.9.1")
        self.assertEqual(deco_for(rn.StepResult(s, False, "x")), "✗ failed")
        self.assertEqual(deco_for(rn.StepResult(s, False, "x", outcome="timed_out")), "✗ timed out")
        self.assertEqual(deco_for(rn.StepResult(s, False, "", outcome="cancelled")), "✗ cancelled")
        self.assertEqual(deco_for(rn.StepResult(s, False, "", outcome="skipped")), "– skipped")
        su = step("waypoints", "uninstall")
        self.assertEqual(
            deco_for(rn.StepResult(su, True, "ok"), op="uninstall"), "✓ removed")

    def test_queued_and_not_in_run(self):
        st = rs.RunState(op="update", steps=[step("a", "update"), step("b", "update")],
                        started=1000.0)
        self.assertEqual(st.row_decoration(row("a"), 0, 1000.0, rs.SPINNER), "· queued")
        self.assertIsNone(st.row_decoration(row("zzz"), 0, 1000.0, rs.SPINNER))

    def test_dim_line_heartbeat_when_silent(self):
        steps = [step("item-a", "update"), step("item-b", "update")]
        st = rs.RunState(op="update", steps=steps, started=1000.0)
        self.assertEqual(st.dim_line(0, 1000.0, 80, rs.SPINNER), "▸ starting…")
        st.on_start(steps[0], 1000.0)
        d0 = st.dim_line(0, 1014.0, 80, rs.SPINNER)
        self.assertIn(shlex.join(steps[0].argv), d0)
        self.assertIn("step 1/1", d0)
        self.assertIn("item 1/2", d0)
        self.assertIn("0:14", d0)
        d1 = st.dim_line(1, 1014.0, 80, rs.SPINNER)
        self.assertNotEqual(d0, d1, "the pulse frame must change the line")

    def test_dim_line_shows_last_output(self):
        st = rs.RunState(op="update", steps=[step("item-a", "update")], started=1000.0)
        st.on_start(st.steps[0], 1000.0)
        st.note_output("Cloning…")
        d = st.dim_line(0, 1001.0, 80, rs.SPINNER)
        self.assertTrue(d.startswith("▸ Cloning…"), d)

    def test_note_output_strips_ansi_and_carriage_returns(self):
        st = rs.RunState(op="update", steps=[step("item-a", "update")], started=1000.0)
        st.on_start(st.steps[0], 1000.0)
        st.note_output("\x1b[32m 45%\r 90%\x1b[0m")
        self.assertEqual(st.last_line, "90%")
        st.note_output("   ")
        self.assertEqual(st.last_line, "90%", "empty lines are ignored")

    def test_dim_line_clamps_to_width(self):
        name = "a-very-long-item-name-0123456789-0123456789"
        st = rs.RunState(op="update", steps=[step(name, "update")], started=1000.0)
        st.on_start(st.steps[0], 1000.0)
        d = st.dim_line(0, 1001.0, 30, rs.SPINNER)
        self.assertLessEqual(rs.cell_width(d), 30)
        self.assertTrue(d.endswith("…"))

    def test_subtitle(self):
        steps = [step(f"item-{i}", "update") for i in range(5)]
        st = rs.RunState(op="update", steps=steps, started=1000.0)
        st.on_start(steps[1], 1041.0)
        self.assertEqual(st.subtitle(1041.0), "⬆️ Update — item 2 of 5 · 0:41")

    def test_note_output_thread_safe(self):
        st = rs.RunState(op="update", steps=[step("item-a", "update")], started=1000.0)
        st.on_start(st.steps[0], 1000.0)

        def hammer(val):
            for _ in range(10000):
                st.note_output(val)

        ths = [threading.Thread(target=hammer, args=(f"line-{i}-",)) for i in range(2)]
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        self.assertIn(st.last_line, ("line-0-", "line-1-"))


if __name__ == "__main__":
    unittest.main()
