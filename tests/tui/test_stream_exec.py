#!/usr/bin/env python3
"""Live-run Task 3 contract: stream_execute streams output lines before exit,
an IDLE timeout kills the whole process group, an immediate stop marks the
result cancelled, non-UTF-8/\\r output still yields clean pieces, and a
missing command is a result, not an exception.

Only sys.executable -c children are spawned (the one allowed real-process
seam); no case waits longer than 3 s.

Usage: pytest tests/tui/test_stream_exec.py -q --durations=5
"""
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from get_haiggoh_tui import runner as rn  # noqa: E402


def _child(code):
    return [sys.executable, "-c", code]


class StreamExecTests(unittest.TestCase):
    def test_lines_stream_before_exit(self):
        lines, times = [], []

        def on_line(line):
            lines.append(line)
            times.append(time.monotonic())

        res = rn.stream_execute(
            _child("import time; print('one', flush=True); time.sleep(0.3); print('two', flush=True)"),
            on_line=on_line)
        t_ret = time.monotonic()
        self.assertEqual(res.returncode, 0)
        self.assertIn("one", res.output)
        self.assertIn("two", res.output)
        self.assertEqual(lines, ["one", "two"])
        self.assertGreaterEqual(t_ret - times[0], 0.2,
                                "the first line must arrive well before the process exits")

    def test_timeout_kills_process_group(self):
        gpids = []

        def on_line(line):
            if line.strip().isdigit():
                gpids.append(int(line.strip()))

        code = ("import subprocess,sys,time;"
                "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);"
                "print(p.pid,flush=True);time.sleep(30)")
        t0 = time.monotonic()
        res = rn.stream_execute(_child(code), on_line=on_line, timeout=1.5, kill_grace=0.3)
        elapsed = time.monotonic() - t0
        self.assertTrue(res.timed_out)
        self.assertLess(elapsed, 3.0, "must return promptly after the idle timeout")
        self.assertTrue(gpids, "the child prints the grandchild pid")
        deadline = time.monotonic() + 1.0
        while True:
            try:
                os.kill(gpids[0], 0)
            except ProcessLookupError:
                break  # grandchild is gone: the process GROUP was killed
            if time.monotonic() > deadline:
                self.fail("grandchild survived — only the direct child was killed")
            time.sleep(0.05)

    def test_idle_timeout_spares_a_chatty_command(self):
        lines = []
        code = "import time\nfor i in range(8):\n    print('l%d' % i, flush=True)\n    time.sleep(0.2)"
        res = rn.stream_execute(_child(code), on_line=lines.append, timeout=1.0)
        self.assertFalse(res.timed_out, "the timeout is idle-based, not a total limit")
        self.assertEqual(res.returncode, 0)
        self.assertEqual(len(lines), 8)

    def test_immediate_cancel_kills(self):
        control = rn.RunControl()
        gpids = []

        def on_line(line):
            if line.strip().isdigit():
                gpids.append(int(line.strip()))

        code = ("import subprocess,sys,time;"
                "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);"
                "print(p.pid,flush=True);time.sleep(30)")

        def stopper():
            # wait until the grandchild exists (its pid was printed), then stop —
            # fixed sleeps race python startup under load
            t0 = time.monotonic()
            while not gpids and time.monotonic() - t0 < 5:
                time.sleep(0.02)
            time.sleep(0.2)
            control.request_stop("immediate")

        th = threading.Thread(target=stopper)
        th.start()
        t0 = time.monotonic()
        res = rn.stream_execute(_child(code), on_line=on_line, control=control)
        elapsed = time.monotonic() - t0
        th.join()
        self.assertTrue(res.cancelled)
        self.assertLess(elapsed, 3.0, "the kill must be prompt (no-kill would take 30 s)")
        self.assertIsNone(control._proc, "detach() ran in the finally")
        self.assertTrue(gpids, "the child printed the grandchild pid")
        deadline = time.monotonic() + 1.0
        while True:
            try:
                os.kill(gpids[0], 0)
            except ProcessLookupError:
                break  # the process GROUP died — killpg, not just the child
            if time.monotonic() > deadline:
                self.fail("grandchild survived — kill_current must killpg the group")
            time.sleep(0.05)

    def test_cancel_after_clean_exit_is_not_cancelled(self):
        # the stop lands while the child is alive, but the child IGNORES SIGTERM
        # and exits 0 on its own — only death BY A SIGNAL may mark cancelled
        control = rn.RunControl()
        seen = []

        def stopper():
            # wait for the child's ready line (SIG_IGN installed) before stopping —
            # a fixed sleep would race python startup under load
            t0 = time.monotonic()
            while "ready" not in seen and time.monotonic() - t0 < 5:
                time.sleep(0.02)
            time.sleep(0.2)
            control.request_stop("immediate")

        th = threading.Thread(target=stopper)
        th.start()
        code = ("import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "print('ready', flush=True); time.sleep(1.0)")
        res = rn.stream_execute(_child(code), on_line=seen.append, control=control)
        th.join()
        self.assertEqual(res.returncode, 0)
        self.assertFalse(res.cancelled, "only death BY A SIGNAL marks cancelled")

    def test_permission_denied_is_a_result_not_an_exception(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "noperm.sh"
            p.write_text("#!/bin/sh\n")
            p.chmod(0o000)
            res = rn.stream_execute([str(p)], on_line=lambda line: None)
        self.assertIsNone(res.returncode)
        self.assertIn("denied", res.output.lower())

    def test_sigkill_escalation_when_sigterm_ignored(self):
        code = ("import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "print('ready', flush=True); time.sleep(5)")
        t0 = time.monotonic()
        res = rn.stream_execute(_child(code), on_line=lambda line: None,
                                timeout=1.2, kill_grace=0.3)
        elapsed = time.monotonic() - t0
        self.assertTrue(res.timed_out)
        self.assertLess(elapsed, 3.0, "SIGTERM ignored ⇒ SIGKILL after kill_grace")

    def test_non_utf8_and_no_newline(self):
        lines = []
        code = "import sys; sys.stdout.buffer.write(b'caf\\xe9\\rdone'); sys.stdout.buffer.flush()"
        rn.stream_execute(_child(code), on_line=lines.append)
        self.assertIn("caf�", lines)
        self.assertIn("done", lines)

    def test_missing_command_is_a_result_not_an_exception(self):
        res = rn.stream_execute(["/nonexistent/brew", "x"], on_line=lambda line: None)
        self.assertIsNone(res.returncode)
        self.assertIn("not found", res.output)


if __name__ == "__main__":
    unittest.main()
