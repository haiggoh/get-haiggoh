#!/usr/bin/env python3
"""Task 5 contract: run all steps after a failure; ok from re-read state not exit code;
self-update writes pending and execs --resume; pending consumed exactly once; skip list.

Usage: python3 -m pytest tests/tui/test_runner.py -q
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import get_haiggoh_core as c  # noqa: E402
from get_haiggoh_tui import runner as rn  # noqa: E402
from get_haiggoh_tui.inventory import Row  # noqa: E402
from get_haiggoh_tui.routes import Step  # noqa: E402


def row(name, status, installed=None, latest=None):
    return Row(name=name, section="plugin", mark="💸", description="d", adds="a",
               installed=installed, latest=latest, status=status, diagnostic=None,
               menu=None, tool=None)


def step(name, op, route="plugin", argv=None, note=None):
    return Step(name=name, op=op, route=route,
                argv=argv if argv is not None else ["claude", "plugin", op, f"{name}@haiggoh"],
                needs_brew=False, note=note)


class _R:
    def __init__(self, rc, out="ok\n", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


class FakeExec:
    def __init__(self, fail_on=()):
        self.calls = []
        self.fail_on = fail_on

    def __call__(self, argv, **kw):
        argv = list(argv)
        self.calls.append(argv)
        if any(f in " ".join(argv) for f in self.fail_on):
            return _R(1, "", "boom")
        return _R(0)


class Reread:
    """Returns `before` on the first call, `after` afterwards (per-step re-reads)."""

    def __init__(self, before, after):
        self.before, self.after = before, after
        self.calls = 0

    def __call__(self, cached):
        self.calls += 1
        return self.before if self.calls == 1 else self.after


class SeqReread:
    """Returns the staged row-lists in order (initial snapshot, then one per step)."""

    def __init__(self, stages):
        self.stages = stages
        self.i = 0

    def __call__(self, cached):
        r = self.stages[min(self.i, len(self.stages) - 1)]
        self.i += 1
        return r


class RunStepsTests(unittest.TestCase):
    def test_failure_midway_runs_the_rest(self):
        before = [row("a", "outdated", "1.0", "2.0"), row("b", "outdated", "1.0", "2.0"),
                  row("c", "outdated", "1.0", "2.0")]
        # each step fixes only its own row; b's execute fails AND its row stays
        # outdated (ok=False) — the rest must still run (a break-on-failure mutant
        # would stop after b and this test goes RED)
        stages = [before,
                  [row("a", "current", "2.0", "2.0"), row("b", "outdated", "1.0", "2.0"),
                   row("c", "outdated", "1.0", "2.0")],
                  [row("a", "current", "2.0", "2.0"), row("b", "outdated", "1.0", "2.0"),
                   row("c", "outdated", "1.0", "2.0")],
                  [row("a", "current", "2.0", "2.0"), row("b", "outdated", "1.0", "2.0"),
                   row("c", "current", "2.0", "2.0")]]
        steps = [step("a", "update"), step("b", "update"), step("c", "update")]
        ex = FakeExec(fail_on=["b@haiggoh"])
        results = rn.run_steps(steps, execute=ex, reread=SeqReread(stages))
        self.assertEqual(len(results), 3)
        self.assertEqual(len(ex.calls), 3, "every step runs even after a failure")
        self.assertEqual([r.ok for r in results], [True, False, True],
                         "ok comes from the re-read state, not the exit code")

    def test_ok_from_reread_not_exit_code(self):
        before = [row("waypoints", "outdated", "0.14.3", "0.15.0")]
        after = [row("waypoints", "outdated", "0.14.3", "0.15.0")]  # unchanged!
        ex = FakeExec()  # exits 0
        results = rn.run_steps([step("waypoints", "update")], execute=ex,
                               reread=Reread(before, after))
        self.assertEqual(ex.calls[0][:3], ["claude", "plugin", "update"])
        self.assertFalse(results[0].ok, "exit 0 but version unchanged must be ok=False")

    def test_uninstall_ok_when_row_gone(self):
        before = [row("waypoints", "current", "0.14.3", "0.14.3")]
        after = [row("waypoints", "missing")]
        results = rn.run_steps([step("waypoints", "uninstall")], execute=FakeExec(),
                               reread=Reread(before, after))
        self.assertTrue(results[0].ok)

    def test_noted_step_is_shown_not_run(self):
        s = step("some-tool", "install", route="brew", argv=[], note="needs 🍺 Homebrew")
        ex = FakeExec()
        before = [row("some-tool", "missing", section=None) if False else row("some-tool", "missing")]
        results = rn.run_steps([s], execute=ex, reread=Reread(before, before))
        self.assertEqual(ex.calls, [], "argv=[] step must not be executed")
        self.assertIn("Homebrew", results[0].output)


class PendingTests(unittest.TestCase):
    def test_write_read_clear_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "pending.json"
            rn.write_pending(p, "update", ["a", "b"])
            data = rn.read_pending(p)
            self.assertEqual(data["schema"], 1)
            self.assertEqual(data["op"], "update")
            self.assertEqual(data["names"], ["a", "b"])
            self.assertIn("created", data)
            rn.clear_pending(p)
            self.assertIsNone(rn.read_pending(p))

    def test_read_pending_corrupt_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "pending.json"
            p.write_text("{nope")
            self.assertIsNone(rn.read_pending(p))

    def test_resume_consumes_pending_once(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "pending.json"
            rn.write_pending(p, "update", ["a"])
            first = rn.consume_pending(p)
            self.assertIsNotNone(first)
            self.assertEqual(first["names"], ["a"])
            self.assertIsNone(rn.consume_pending(p), "consumed exactly once")

    def test_leftover_pending_is_not_replayed_without_flag(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "pending.json"
            rn.write_pending(p, "update", ["a"])
            before = [row("a", "outdated", "1.0", "2.0")]
            after = [row("a", "current", "2.0", "2.0")]
            ex = FakeExec()
            rn.run_steps([step("a", "update")], execute=ex, reread=Reread(before, after))
            # a plain run must NOT consume the leftover pending file
            self.assertIsNotNone(rn.read_pending(p))


class SelfUpdateTests(unittest.TestCase):
    def test_self_update_writes_pending_and_execs_resume(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "pending.json"
            steps = [step("get-haiggoh", "update"), step("waypoints", "update")]
            ex = FakeExec()
            execs = []

            def fake_execv(path, argv):
                execs.append((path, list(argv)))

            before = [row("get-haiggoh", "outdated", "0.9.4", "0.10.0"),
                      row("waypoints", "outdated", "0.14.3", "0.15.0")]
            after = [row("get-haiggoh", "current", "0.10.0", "0.10.0"),
                     row("waypoints", "current", "0.15.0", "0.15.0")]
            ok = rn.self_update_then_relaunch(steps, p, execv=fake_execv, execute=ex,
                                              reread=Reread(before, after))
            self.assertTrue(ok)
            data = rn.read_pending(p)
            self.assertEqual(data["names"], ["waypoints"], "pending carries the REST")
            self.assertEqual(len(execs), 1)
            self.assertIn("--resume", execs[0][1])
            self.assertIn("get-haiggoh-tui", execs[0][0])

    def test_no_resume_when_self_is_alone(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "pending.json"
            execs = []
            ok = rn.self_update_then_relaunch([step("get-haiggoh", "update")], p,
                                              execv=lambda *a: execs.append(a))
            self.assertFalse(ok)
            self.assertEqual(execs, [])
            self.assertIsNone(rn.read_pending(p))


class SkipListTests(unittest.TestCase):
    def test_uninstall_adds_to_skip_list(self):
        with tempfile.TemporaryDirectory() as d:
            skipf = Path(d) / "skip.json"
            skipf.write_text("{}")
            with mock.patch.dict(os.environ, {"GET_HAIGGOH_SKIP_FILE": str(skipf)}):
                before = [row("waypoints", "current", "0.14.3", "0.14.3")]
                after = [row("waypoints", "missing")]
                results = rn.run_steps([step("waypoints", "uninstall")], execute=FakeExec(),
                                       reread=Reread(before, after))
                self.assertTrue(results[0].ok)
                skip = json.loads(skipf.read_text())
                self.assertEqual(skip.get("waypoints"), "both")

    def test_install_removes_from_skip_list(self):
        with tempfile.TemporaryDirectory() as d:
            skipf = Path(d) / "skip.json"
            skipf.write_text(json.dumps({"waypoints": "both"}))
            with mock.patch.dict(os.environ, {"GET_HAIGGOH_SKIP_FILE": str(skipf)}):
                before = [row("waypoints", "missing")]
                after = [row("waypoints", "current", "0.14.3", "0.14.3")]
                results = rn.run_steps([step("waypoints", "install")], execute=FakeExec(),
                                       reread=Reread(before, after))
                self.assertTrue(results[0].ok)
                self.assertNotIn("waypoints", json.loads(skipf.read_text()))


if __name__ == "__main__":
    unittest.main()
