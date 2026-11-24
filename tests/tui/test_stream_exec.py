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
        res = rn.stream_execute(_child(code), on_line=on_line, timeout=0.5, kill_grace=0.2)
        elapsed = time.monotonic() - t0
        self.assertTrue(res.timed_out)
        self.assertLess(elapsed, 2.0, "must return promptly after the idle timeout")
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
        res = rn.stream_execute(_child(code), on_line=lines.append, timeout=0.5)
        self.assertFalse(res.timed_out, "the timeout is idle-based, not a total limit")
        self.assertEqual(res.returncode, 0)
        self.assertEqual(len(lines), 8)

    def test_immediate_cancel_kills(self):
        control = rn.RunControl()

        def stopper():
            time.sleep(0.3)
            control.request_stop("immediate")

        th = threading.Thread(target=stopper)
        th.start()
        t0 = time.monotonic()
        res = rn.stream_execute(_child("import time; time.sleep(30)"),
                                on_line=lambda line: None, control=control)
        elapsed = time.monotonic() - t0
        th.join()
        self.assertTrue(res.cancelled)
        self.assertLess(elapsed, 1.5)

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
