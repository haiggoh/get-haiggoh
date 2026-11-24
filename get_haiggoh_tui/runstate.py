"""get_haiggoh_tui.runstate — the live-run model and every string the UI paints.

PURE module: stdlib only, no Textual, no rich — so rendering is unit-testable
under any pytest. Consumes Step (routes) and StepResult (runner).
"""
from __future__ import annotations

import os
import re
import shlex
import threading
import unicodedata
from dataclasses import dataclass, field

from .routes import Step
from .runner import StepResult

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
ASCII_SPINNER = "|/-\\"
PULSE = "▁▂▃▄▅▆▇█▇▆▅▄▃▂"
EMOJI = {"update": "⬆️", "install": "📥", "uninstall": "🗑️"}

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")


def spinner_frames(env=os.environ) -> str:
    """Braille spinner; ASCII only when the effective locale (first non-empty of
    LC_ALL, LC_CTYPE, LANG) is exactly C or POSIX."""
    loc = next((env.get(k) for k in ("LC_ALL", "LC_CTYPE", "LANG") if env.get(k)), "")
    return ASCII_SPINNER if loc in ("C", "POSIX") else SPINNER


def bar(done: int, total: int, width: int = 10) -> str:
    """▐ + █×done + ░×rest; total==0 ⇒ all ░."""
    k = round(width * done / total) if total else 0
    k = max(0, min(width, k))
    return "▐" + "█" * k + "░" * (width - k)


def fmt_elapsed(seconds: float) -> str:
    t = int(seconds)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def cell_width(s: str) -> int:
    """Terminal cells: East-Asian W/F ⇒ 2, combining/format Mn/Me/Cf ⇒ 0, else 1."""
    w = 0
    for ch in s:
        cat = unicodedata.category(ch)
        if cat in ("Mn", "Me", "Cf"):
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def clamp(s: str, width: int) -> str:
    """≤ width cells, single line, trailing … when cut — never wraps."""
    if width <= 0:
        return ""
    if cell_width(s) <= width:
        return s
    out, w = "", 0
    for ch in s:
        cw = cell_width(ch)
        if w + cw > width - 1:
            break
        out += ch
        w += cw
    return out + "…"


@dataclass
class RunState:
    op: str
    steps: list[Step]
    started: float
    items: list[str] = field(init=False)          # unique names, step order
    current: Step | None = None
    step_started: float | None = None
    results: list[StepResult] = field(default_factory=list)
    stop: str | None = None
    finished: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _last_line: str = ""

    def __post_init__(self):
        seen: list[str] = []
        for s in self.steps:
            if s.name not in seen:
                seen.append(s.name)
        self.items = seen

    # ---- events (called from the worker, bridged to the UI thread) ----

    def on_start(self, step: Step, now: float) -> None:
        with self._lock:
            self.current = step
            self.step_started = now
            self._last_line = ""   # a new step clears the previous line

    def on_result(self, result: StepResult) -> None:
        with self._lock:
            self.results.append(result)

    def note_output(self, line: str) -> None:
        """Thread-safe: strips ANSI CSI/OSC, keeps the text after the last \\r,
        strips whitespace, ignores empty lines."""
        text = _ANSI_RE.sub("", line).rsplit("\r", 1)[-1].strip()
        if not text:
            return
        with self._lock:
            self._last_line = text

    @property
    def last_line(self) -> str:
        with self._lock:
            return self._last_line

    # ---- queries ----

    def item_steps(self, name: str) -> tuple[int, int]:
        """(done, total) steps of one item."""
        total = sum(1 for s in self.steps if s.name == name)
        done = sum(1 for r in self.results if r.step.name == name)
        return done, total

    def item_position(self) -> tuple[int, int]:
        """(1-based index of the current item, number of items)."""
        i = self.items.index(self.current.name) + 1 if self.current else 1
        return i, len(self.items)

    def outcome_of(self, name: str) -> str | None:
        """None until all of the item's steps have results; then 'ok' if all ok,
        else the first non-ok outcome."""
        rs = [r for r in self.results if r.step.name == name]
        total = sum(1 for s in self.steps if s.name == name)
        if len(rs) < total:
            return None
        if all(r.ok for r in rs):
            return "ok"
        return next(r.outcome for r in rs if not r.ok)

    # ---- painted strings ----

    def row_decoration(self, row, frame: int, now: float, frames: str) -> str | None:
        """None when the row is not in the run. Finished rows flip to ✓/✗ as soon
        as all of the item's steps have results; the current item's row runs."""
        if row.name not in self.items:
            return None
        outcome = self.outcome_of(row.name)
        if outcome is not None:
            if outcome == "ok":
                item_results = [r for r in self.results if r.step.name == row.name]
                if item_results[-1].step.op == "uninstall":
                    return "✓ removed"
                after = item_results[-1].after_version
                return f"✓ {after or row.installed or ''}".rstrip()
            return {"failed": "✗ failed", "timed_out": "✗ timed out",
                    "cancelled": "✗ cancelled", "skipped": "– skipped"}[outcome]
        if self.current is not None and self.current.name == row.name:
            done, total = self.item_steps(row.name)
            spin = frames[frame % len(frames)]
            b = bar(done, total)
            if self.current.op == "uninstall":
                return f"{spin} {b} removing"
            target = row.latest or "?"
            return f"{spin} {b} {row.installed or '—'} → {target}"
        return "· queued"

    def dim_line(self, frame: int, now: float, width: int, frames: str) -> str:
        if self.current is None or self.step_started is None:
            return clamp("▸ starting…", width)
        text = self.last_line or (shlex.join(self.current.argv)
                                  if self.current.argv else (self.current.note or ""))
        done, total = self.item_steps(self.current.name)
        i, n_items = self.item_position()
        s = (f"▸ {text} · step {done + 1}/{total} · item {i}/{n_items} · "
             f"{fmt_elapsed(now - self.step_started)} {PULSE[frame % len(PULSE)]}")
        return clamp(s, width)

    def subtitle(self, now: float) -> str:
        i, n = self.item_position()
        return (f"{EMOJI[self.op]} {self.op.capitalize()} — item {i} of {n} · "
                f"{fmt_elapsed(now - self.started)}")
