#!/usr/bin/env python3
"""Shared live-run pilot rig. The name deliberately does NOT match the test glob,
so pytest never collects it. Imported by test_live_run.py and test_live_run_cancel.py.
"""
from __future__ import annotations

import dataclasses
import threading
import time

from get_haiggoh_tui import runner as rn

_WAIT_WATCHDOG = 10.0  # a gated runner must never hang the suite, even on a failed assert


class GatedRunner:
    """A runner fake that holds the run open until `release` is set.

    Per step: emits ("start", step), sets `started`, emits each line as
    ("output", step, line), waits for `release` in 0.02 s slices (ending early
    when control.stop == "immediate"), then emits a ("result", StepResult) whose
    after_row is the step's row from the `rows` kwarg at installed="9.9" /
    status="current".

    It deliberately has NO stop-skipping logic of its own: the authoritative stop
    semantics are Task 2's tests against the real run_steps. The one concession is
    that a result emitted while control.stop is set is LABELLED cancelled/skipped
    (and later items skipped) so the UI report can render what a real stop looks
    like — the decision logic stays in run_steps, not here.

    gate_after_result=True blocks after each result until `after_result` is set
    (used to observe the row flip deterministically while the run is still open).
    """

    def __init__(self, lines=("resolving…",), outcome="ok", raise_exc=None,
                 result_output=None, gate_after_result=False):
        self.lines = list(lines)
        self.outcome = outcome            # "ok" | "failed" | … or {name: outcome}
        self.raise_exc = raise_exc
        self.result_output = result_output
        self.gate_after_result = gate_after_result
        self.calls: list[list[str]] = []
        self.kwargs: list[dict] = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.after_result = threading.Event()

    def _outcome_for(self, s) -> str:
        if isinstance(self.outcome, dict):
            return self.outcome.get(s.name, "ok")
        return self.outcome

    def _result(self, s, outcome: str) -> rn.StepResult:
        rows = self.kwargs[-1].get("rows") if self.kwargs else None
        before = next((r for r in (rows or []) if r.name == s.name), None)
        after = (dataclasses.replace(before, installed="9.9", status="current")
                 if before is not None else None)
        output = self.result_output if self.result_output is not None else "\n".join(self.lines)
        ok = outcome == "ok"
        return rn.StepResult(s, ok, output, outcome=("" if ok else outcome), after_row=after)

    def __call__(self, steps, on_event=lambda e: None, control=None, timeout=None, **kw):
        self.calls.append([s.name for s in steps])
        self.kwargs.append(dict(kw))
        prev_name = None
        results: list[rn.StepResult] = []
        for s in steps:
            stop = control.stop if control is not None else None
            if stop == "immediate" or (stop == "after_current" and prev_name is not None
                                        and s.name != prev_name):
                outcome = "cancelled" if stop == "immediate" else "skipped"
                res = self._result(s, outcome)
                results.append(res)
                on_event(("result", res))
                continue
            on_event(("start", s))
            for ln in self.lines:
                on_event(("output", s, ln))
            self.started.set()  # only after the lines, so readers see a settled state
            t0 = time.monotonic()
            while not self.release.is_set():
                if control is not None and control.stop == "immediate":
                    break
                if time.monotonic() - t0 > _WAIT_WATCHDOG:
                    raise AssertionError("gated runner watchdog expired (release never set)")
                self.release.wait(0.02)
            prev_name = s.name
            if self.raise_exc is not None:
                raise self.raise_exc
            outcome = self._outcome_for(s)
            if control is not None and control.stop == "immediate":
                outcome = "cancelled"
            res = self._result(s, outcome)
            results.append(res)
            on_event(("result", res))
            if self.gate_after_result:
                t1 = time.monotonic()
                while not self.after_result.is_set():
                    if control is not None and control.stop == "immediate":
                        break
                    if time.monotonic() - t1 > _WAIT_WATCHDOG:
                        raise AssertionError("gated runner watchdog expired (after_result never set)")
                    self.after_result.wait(0.02)
        return results
