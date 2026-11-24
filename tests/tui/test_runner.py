#!/usr/bin/env python3
"""Task 5 contract: run all steps after a failure; ok from re-read state not exit code;
self-update writes pending and execs --resume; pending consumed exactly once; skip list.

Usage: python3 -m pytest tests/tui/test_runner.py -q
"""
import dataclasses
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
        before = [row("some-tool", "missing")]
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


class FakeStream:
    """Stream-seam fake: records argv calls, emits lines_by_name through on_line,
    returns results_by_name (default: rc 0 with the lines as output)."""

    def __init__(self, lines_by_name=None, results_by_name=None):
        self.calls = []
        self.lines_by_name = lines_by_name or {}
        self.results_by_name = results_by_name or {}

    def _key(self, argv):
        tail = " ".join(str(a) for a in argv)
        for name in list(self.lines_by_name) + list(self.results_by_name):
            if name in tail:
                return name
        return None

    def __call__(self, argv, *, on_line, control=None, timeout=None):
        argv = list(argv)
        self.calls.append(argv)
        key = self._key(argv)
        lines = self.lines_by_name.get(key, []) if key else []
        for ln in lines:
            on_line(ln)
        if key is not None and key in self.results_by_name:
            return self.results_by_name[key]
        return rn.ExecResult(0, "".join(line + "\n" for line in lines))


class LiveRunTests(unittest.TestCase):
    """Live-run contract: streaming events, RunControl stop modes, step outcomes,
    and the local (reread_one) re-read mode that never calls the full reread."""

    @staticmethod
    def _bump(before):
        return dataclasses.replace(before, installed=before.latest or before.installed,
                                   status="current")

    def test_events_in_order_with_output(self):
        a, b = step("item-a", "update"), step("item-b", "update")
        fs = FakeStream(lines_by_name={"item-a": ["a", "b"]})
        events = []
        rows = [row("item-a", "outdated", "1.0", "2.0"), row("item-b", "outdated", "1.0", "2.0")]
        results = rn.run_steps([a, b], stream=fs, on_event=events.append,
                               rows=rows, reread_one=self._bump)
        self.assertEqual([e[0] for e in events],
                         ["start", "output", "output", "result", "start", "result"])
        self.assertEqual(events[1], ("output", a, "a"))
        self.assertEqual(events[2], ("output", a, "b"))
        self.assertEqual(len(results), 2)

    def test_execute_given_keeps_legacy_path(self):
        steps = [step("item-a", "update"), step("item-b", "update")]
        ex, fs = FakeExec(), FakeStream()
        before = [row("item-a", "outdated", "1.0", "2.0"), row("item-b", "outdated", "1.0", "2.0")]
        after = [row("item-a", "current", "2.0", "2.0"), row("item-b", "current", "2.0", "2.0")]
        rn.run_steps(steps, execute=ex, stream=fs, reread=Reread(before, after))
        self.assertEqual(ex.calls, [s.argv for s in steps])
        self.assertEqual(fs.calls, [], "stream must not be called when execute is given")

    def test_stop_after_current_finishes_item_then_skips(self):
        fa_plugin = step("free-agents", "update", route="plugin")
        fa_brew = step("free-agents", "update", route="brew",
                       argv=["brew", "upgrade", "haiggoh/tap/free-agents"])
        wp = step("waypoints", "update")
        control = rn.RunControl()
        fs = FakeStream()

        def on_event(e):
            if e[0] == "start" and e[1] is fa_plugin:
                control.request_stop("after_current")

        rows = [row("free-agents", "outdated", "0.1", "0.2"),
                row("waypoints", "outdated", "0.14.3", "0.15.0")]
        results = rn.run_steps([fa_plugin, fa_brew, wp], stream=fs, on_event=on_event,
                               control=control, rows=rows, reread_one=self._bump)
        self.assertEqual(control.stop, "after_current")
        self.assertIn(results[0].outcome, ("ok", "failed"))
        self.assertIn(results[1].outcome, ("ok", "failed"), "the two-step item finishes")
        self.assertEqual(results[2].outcome, "skipped")
        self.assertFalse(results[2].ok)
        self.assertEqual(len(fs.calls), 2, "stream called for the two steps of the item only")

    def test_stop_immediate_skips_rest(self):
        steps = [step("item-a", "update"), step("item-b", "update"), step("item-c", "update")]
        control = rn.RunControl()
        fs = FakeStream(results_by_name={"item-a": rn.ExecResult(None, "", cancelled=True)})

        def on_event(e):
            if e[0] == "start" and e[1] is steps[0]:
                control.request_stop("immediate")

        rows = [row(n, "outdated", "1.0", "2.0") for n in ("item-a", "item-b", "item-c")]
        results = rn.run_steps(steps, stream=fs, on_event=on_event, control=control,
                               rows=rows, reread_one=self._bump)
        self.assertEqual([r.outcome for r in results], ["cancelled", "skipped", "skipped"])
        self.assertEqual([r.ok for r in results], [False, False, False])
        self.assertEqual(len(fs.calls), 1)

    def test_timed_out_outcome(self):
        steps = [step("item-a", "update"), step("item-b", "update")]
        fs = FakeStream(results_by_name={"item-a": rn.ExecResult(-15, "partial", timed_out=True)})
        rows = [row("item-a", "outdated", "1.0", "2.0"), row("item-b", "outdated", "1.0", "2.0")]
        seen = []

        def reread_one(b):
            seen.append(b)
            return self._bump(b)

        results = rn.run_steps(steps, stream=fs, rows=rows, reread_one=reread_one)
        self.assertEqual(results[0].outcome, "timed_out")
        self.assertFalse(results[0].ok)
        self.assertIsNotNone(results[0].after_row, "timed_out still re-reads state for the row")
        self.assertEqual(len(seen), 2, "one reread per step, timed_out included")
        self.assertEqual(len(results), 2, "the queue continues after a timeout")
        self.assertEqual(len(fs.calls), 2)

    def test_after_version_from_reread(self):
        before = [row("waypoints", "outdated", "0.14.3", "0.15.0")]
        after = [row("waypoints", "current", "0.15.0", "0.15.0")]
        results = rn.run_steps([step("waypoints", "update")], execute=FakeExec(),
                               reread=Reread(before, after))
        self.assertEqual(results[0].after_version, "0.15.0")
        after_row = results[0].after_row
        self.assertIsNotNone(after_row)
        self.assertEqual(after_row.installed, "0.15.0")

    def test_local_mode_never_calls_full_reread(self):
        def reread(cached):
            raise AssertionError("network sweep")

        before_row = row("waypoints", "outdated", "0.14.3", "0.15.0")
        seen = []

        def reread_one(b):
            seen.append(b)
            return dataclasses.replace(b, installed="0.15.0", status="current")

        results = rn.run_steps([step("waypoints", "update")], stream=FakeStream(),
                               reread=reread, rows=[before_row], reread_one=reread_one)
        self.assertTrue(results[0].ok)
        self.assertEqual(seen, [before_row], "reread_one called once, with the BEFORE row")

    def test_local_mode_keeps_latest_from_before(self):
        before_row = row("waypoints", "outdated", "0.14.3", "0.15.0")

        def reread_one(b):
            return dataclasses.replace(b, installed="0.14.9")

        results = rn.run_steps([step("waypoints", "update")], stream=FakeStream(),
                               rows=[before_row], reread_one=reread_one)
        self.assertFalse(results[0].ok, "0.14.9 is still behind the known latest 0.15.0")

    def test_local_mode_reread_one_raises(self):
        def reread_one(b):
            raise RuntimeError("boom")

        steps = [step("item-a", "update"), step("item-b", "update")]
        rows = [row("item-a", "outdated", "1.0", "2.0"), row("item-b", "outdated", "1.0", "2.0")]
        results = rn.run_steps(steps, stream=FakeStream(), rows=rows, reread_one=reread_one)
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].outcome, "failed")
        self.assertEqual(len(results), 2, "the next step still runs")

    def test_local_mode_requires_rows(self):
        with self.assertRaises(ValueError):
            rn.run_steps([step("item-a", "update")], stream=FakeStream(),
                         reread_one=lambda b: b)

    def test_step_result_positional_compat(self):
        s = step("item-a", "update")
        self.assertEqual(rn.StepResult(s, True, "ok").outcome, "ok")
        self.assertEqual(rn.StepResult(s, False, "x").outcome, "failed")

    def test_run_control_stop_modes(self):
        ctl = rn.RunControl()
        self.assertIsNone(ctl.stop)
        ctl.request_stop("after_current")
        self.assertEqual(ctl.stop, "after_current")
        ctl.request_stop("immediate")
        self.assertEqual(ctl.stop, "immediate")
        ctl.request_stop("after_current")
        self.assertEqual(ctl.stop, "immediate", "never downgrades")

    def test_all_routes_stream_when_execute_none(self):
        git_s = step("item-git", "install", route="git", argv=["git", "clone", "https://x"])
        rel_s = step("item-rel", "install", route="release-installer", argv=[])
        fs = FakeStream()
        rows = [row("item-git", "missing"), row("item-rel", "missing")]
        with mock.patch.object(rn, "_prepare_release_installer",
                               lambda s, r: ("", Path("/tmp/asset.sh"))):
            rn.run_steps([git_s, rel_s], stream=fs, rows=rows, reread_one=self._bump)
        self.assertEqual(fs.calls, [["git", "clone", "https://x"], ["/bin/bash", "/tmp/asset.sh"]],
                         "git and release-installer argvs go through the stream seam too")

    def test_skipped_steps_do_not_reread_and_have_empty_output(self):
        steps = [step("item-a", "update"), step("item-b", "update"), step("item-c", "update")]
        control = rn.RunControl()
        fs = FakeStream(results_by_name={"item-a": rn.ExecResult(None, "", cancelled=True)})
        seen = []

        def reread_one(b):
            seen.append(b)
            return self._bump(b)

        def on_event(e):
            if e[0] == "start" and e[1] is steps[0]:
                control.request_stop("immediate")

        rows = [row(n, "outdated", "1.0", "2.0") for n in ("item-a", "item-b", "item-c")]
        results = rn.run_steps(steps, stream=fs, on_event=on_event, control=control,
                               rows=rows, reread_one=reread_one)
        self.assertEqual([r.outcome for r in results], ["cancelled", "skipped", "skipped"])
        self.assertEqual(results[1].output, "")
        self.assertEqual(results[2].output, "")
        self.assertEqual(len(seen), 1, "only the run step re-reads; skipped steps never do")

    def test_local_mode_rereads_only_the_current_steps_row(self):
        fa_plugin = step("free-agents", "update", route="plugin")
        fa_brew = step("free-agents", "update", route="brew",
                       argv=["brew", "upgrade", "haiggoh/tap/free-agents"])
        wp = step("waypoints", "update")
        seen = []

        def reread_one(b):
            seen.append(b)
            return self._bump(b)

        rows = [row("free-agents", "outdated", "0.1", "0.2"),
                row("waypoints", "outdated", "0.14.3", "0.15.0")]
        rn.run_steps([fa_plugin, fa_brew, wp], stream=FakeStream(), rows=rows, reread_one=reread_one)
        self.assertEqual([b.name for b in seen], ["free-agents", "free-agents", "waypoints"],
                         "exactly one reread per step, and it is that step's row")
        self.assertEqual(seen[0].installed, "0.1")
        self.assertEqual(seen[1].installed, "0.2",
                         "the item's second step sees the first step's AFTER row as its before-row")

    def test_timed_out_wins_over_cancelled(self):
        fs = FakeStream(results_by_name={
            "item-a": rn.ExecResult(-15, "", timed_out=True, cancelled=True)})
        rows = [row("item-a", "outdated", "1.0", "2.0")]
        results = rn.run_steps([step("item-a", "update")], stream=fs, rows=rows,
                               reread_one=self._bump)
        self.assertEqual(results[0].outcome, "timed_out", "timed_out is checked first")


if __name__ == "__main__":
    unittest.main()
