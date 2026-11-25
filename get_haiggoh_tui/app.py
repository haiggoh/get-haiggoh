"""get_haiggoh_tui.app — the Textual app (the ONLY module besides screens.py that imports Textual).

Task 7 of docs/superpowers/plans/2026-11-08-tui-01-get-haiggoh-tui.md. Collaborators are
injectable (rows_loader, runner, menu_for, legacy_runner, installer_runner,
verify_installed, execv) so pilot tests never touch real claude/brew/network.
Paint comes from rows_loader(cached=True); a worker refreshes with cached=False.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from textual import work
from textual.app import App
from textual.geometry import Region

from . import screens as scr
from .brew_gate import needs_brew
from .inventory import Row
from .menuspec import menu_for
from .routes import SELF_NAME, brew_path, plan_steps
from .runner import (RunControl, consume_pending, read_pending, relaunch_with_pending,
                     run_steps, step_timeout_from_env)
from .runstate import RunState
from .selection import mark_first_run_done
from .status import build_rows, reread_row


def _state_path() -> Path:
    return Path(os.environ.get("GET_HAIGGOH_TUI_STATE_FILE")
                or "~/.claude/.get-haiggoh-tui-state.json").expanduser()


def _pending_path() -> Path:
    return Path(os.environ.get("GET_HAIGGOH_TUI_PENDING_FILE")
                or "~/.claude/.get-haiggoh-tui-pending.json").expanduser()


_STATUS_TEXT = {"current": "✓", "missing": "not installed", "unverified": "? unverified"}


# Stray `p` on Apple Terminal — PORTED from free-agents bin/session_picker_terminal.py
# (CHANGELOG 0.22.0 "stray `p` on Apple Terminal (for real this time)"). Textual 3.7.1's
# LinuxDriver sends the DECRQM query ESC[?2048$p unconditionally; Apple Terminal does not
# consume it and prints the trailing `p`. (The 2026 query is already guarded upstream.)
try:
    from textual.drivers.linux_driver import LinuxDriver
except ImportError:  # non-POSIX: Textual picks its own driver
    LinuxDriver = None  # type: ignore[assignment,misc]

if LinuxDriver is not None:
    class AppleTerminalSafeDriver(LinuxDriver):  # type: ignore[misc,valid-type]
        def _query_in_band_window_resize(self) -> None:
            if os.environ.get("TERM_PROGRAM", "") == "Apple_Terminal":
                return
            super()._query_in_band_window_resize()
else:
    AppleTerminalSafeDriver = None  # type: ignore[assignment,misc]


def get_driver_class():
    """The safe driver on POSIX (it is a pass-through outside Apple Terminal), else None."""
    return AppleTerminalSafeDriver


MODES = ("update", "install", "uninstall")

# An emoji cluster is built from these categories: So (the symbol), Sk (skin-tone
# modifier), Cf (zero-width joiner), Mn (variation selector U+FE0F).
_EMOJI_CATS = {"So", "Sk", "Cf", "Mn"}


def strip_leading_emoji(text: str) -> str:
    """Drop a leading emoji cluster and the spaces after it. The info box's title line
    already carries the brand mark, so a description that opens with an emoji showed it
    twice (user 2026-11-09). Decided by the text's own leading characters, never by matching
    the mark (they come from different files), so a description whose emoji changes can't
    bring the duplicate back. Returns the text unchanged if nothing would be left."""
    import unicodedata
    i = 0
    while i < len(text) and unicodedata.category(text[i]) in _EMOJI_CATS:
        i += 1
    rest = text[i:].lstrip()
    return rest if i and rest else text


class GetHaiggohApp(App):
    """CSL-style TUI listing every haiggoh plugin and related tool."""

    CSS_PATH = "theme.tcss"

    def __init__(self, rows_loader=build_rows, runner=run_steps, state_path=None,
                 pending_path=None, brew_present=None, resume=False, menu_for=menu_for,
                 legacy_runner=None, installer_runner=None, verify_installed=None,
                 execv=None, suspend_fn=None, reread_one=None):
        # CSL's current look (session_picker.py R5): textual-ansi theme + ANSI colours, so
        # no painted background — the terminal's own light/dark theme shows through
        # driver_class MUST go through __init__: Textual's App.__init__ assigns
        # self.driver_class = driver_class or self.get_driver_class(), so a class attribute
        # is overwritten (free-agents 786d487 shipped that and kept the stray `p`)
        super().__init__(driver_class=get_driver_class(), ansi_color=True)
        self.theme = "textual-ansi"
        try:
            self.version = json.loads(
                (Path(__file__).resolve().parents[1] / ".claude-plugin" / "plugin.json")
                .read_text(encoding="utf-8"))["version"]
        except Exception:
            self.version = "?"
        # suspend_fn: the App.suspend() context manager (headless tests inject a fake)
        self.suspend_fn = suspend_fn or self.suspend
        self.rows_loader = rows_loader
        self.runner = runner
        self.state_path = Path(state_path) if state_path else _state_path()
        self.pending_path = Path(pending_path) if pending_path else _pending_path()
        self.brew_present = (brew_path() is not None) if brew_present is None else brew_present
        self.brew_allowed = False
        self._brew_declined = False
        self.resume = resume
        self.menu_for = menu_for
        self.legacy_runner = legacy_runner
        self.installer_runner = installer_runner
        self.verify_installed = verify_installed or (lambda: brew_path() is not None)
        self.execv = execv
        self.reread_one = reread_one if reread_one is not None else reread_row
        self.run_state: RunState | None = None
        self._run_control: RunControl | None = None
        self._relaunch_rest = None
        self._carried_results = None
        self._run_op = "update"
        self.rows: list[Row] = []
        self.ticks: set[str] = set()
        self.summary = ""
        self.decline_lines: list[str] = []
        self.refresh_failed = False
        self._info_name: str | None = None
        self._pending_op = "update"
        # browse mode (None): no checkboxes, enter opens an item's menu. A mode in MODES:
        # checkboxes on eligible rows, enter / the same key again runs it, esc/b leaves.
        self.mode: str | None = None
        # app rows launch through `open` (own window); tests replace this
        self.app_opener = lambda argv: __import__("subprocess").run(argv, check=False)

    # --- lifecycle ---------------------------------------------------------
    def on_mount(self):
        pending = read_pending(self.pending_path)
        if pending and not self.resume:
            self.push_screen(scr.ResumeScreen(pending))
            return
        if pending and self.resume:
            data = consume_pending(self.pending_path)
            if data:
                self._pending_op = data.get("op", "update")
                self.ticks = set(data.get("names") or [])
        self.start_main()

    def start_main(self):
        self.rows = list(self.rows_loader(True))  # instant paint from cache
        # ticks are chosen when a mode is entered (enter_mode), not at startup; a resumed
        # pending run re-enters its own mode with its own names
        resumed = set(self.ticks)
        self.ticks = set()
        mark_first_run_done(self.state_path)  # after the first paint
        self.refresh_summary()
        self.push_screen(scr.MainScreen())
        if resumed and self._pending_op in MODES:
            self.enter_mode(self._pending_op, resumed)
        self._refresh_worker()

    # --- modes ---------------------------------------------------------------
    def eligible(self, r: Row, mode: str | None = None) -> bool:
        mode = mode or self.mode
        if mode == "update":
            return r.status == "outdated"
        if mode == "install":
            return r.status == "missing"
        if mode == "uninstall":
            return r.status in ("current", "outdated", "unverified")
        return False

    def enter_mode(self, mode: str, ticks: set[str] | None = None):
        """Update/install start with every eligible row ticked; uninstall starts empty
        (destructive). A resumed run passes its own names."""
        self.mode = mode
        if ticks is not None:
            self.ticks = {n for n in ticks if any(r.name == n for r in self.rows)}
        elif mode == "uninstall":
            self.ticks = set()
        else:
            self.ticks = {r.name for r in self.rows if self.eligible(r, mode)}
        self._redraw_main()

    def leave_mode(self):
        self.mode = None
        self.ticks = set()
        self._redraw_main()

    def _redraw_main(self):
        screen = self.screen
        if isinstance(screen, scr.MainScreen):
            screen.apply_mode()
            screen.rebuild_rows()
            self.refresh_buttons()

    @work(exit_on_error=False, thread=True)
    def _refresh_worker(self):
        """Background refresh with cached=False; a failure shows in the summary line,
        never crashes the paint."""
        try:
            rows = list(self.rows_loader(False))
        except Exception:
            self.call_from_thread(self._mark_refresh_failed)
            return
        self.call_from_thread(self._apply_rows, rows)

    def _mark_refresh_failed(self):
        self.refresh_failed = True
        self.refresh_summary()

    def _apply_rows(self, rows):
        self.rows = rows
        self.refresh_summary()
        screen = self.screen
        if isinstance(screen, scr.MainScreen):
            screen.rebuild_rows()
            self.refresh_buttons()

    # --- summary / info box --------------------------------------------------
    def refresh_summary(self):
        if self.refresh_failed and not self.rows:
            self.summary = "couldn't check for updates"
        else:
            up = sum(1 for r in self.rows if r.status == "outdated")
            miss = sum(1 for r in self.rows if r.status == "missing")
            self.summary = f"{up} updates available · {miss} not installed"
            if self.refresh_failed:
                self.summary += " (couldn't check for updates)"
        screen = self.screen
        if isinstance(screen, scr.MainScreen):
            from textual.widgets import Static
            screen.query_one("#summary", Static).update(self.summary)

    def show_info_for(self, name: str):
        self._info_name = name
        screen = self.screen
        if isinstance(screen, scr.MainScreen):
            from textual.widgets import Static
            info = screen.query_one("#info", Static)
            text = self.info_text()
            info.update(text)
            info.display = bool(text)  # CSL: no empty frame before the first highlight

    def info_text(self) -> str:
        r = next((x for x in self.rows if x.name == self._info_name), None)
        if not r:
            return ""
        status = _STATUS_TEXT.get(r.status) or f"latest {r.latest}"
        lines = [f"{r.mark} {r.name} — installed {r.installed or 'not installed'} {status}",
                 strip_leading_emoji(r.description or ""), f"Adds: {r.adds}"]
        if r.status == "missing":
            steps = plan_steps([r], {r.name}, "install", self.brew_present, self.brew_allowed)
            route = steps[0].route if steps else "?"
            lines.append(f"Installs via {route}")
        if self.decline_lines:
            lines.append("")
            lines.extend(self.decline_lines)
        return "\n".join(lines)

    def refresh_buttons(self):
        screen = self.screen
        if not isinstance(screen, scr.MainScreen):
            return
        def count(mode):
            if self.mode == mode:  # in a mode: what is ticked
                return sum(1 for r in self.rows if r.name in self.ticks and self.eligible(r, mode))
            return sum(1 for r in self.rows if self.eligible(r, mode))  # browse: what is available
        screen.query_one("#btn-update").label = f"Update {count('update')}"
        screen.query_one("#btn-install").label = f"Install {count('install')}"
        screen.query_one("#btn-uninstall").label = (
            f"Uninstall {count('uninstall')}" if self.mode == "uninstall" else "Uninstall")

    # --- bulk operations -----------------------------------------------------
    def run_op(self, op: str):
        steps = plan_steps(self.rows, self.ticks, op, self.brew_present, self.brew_allowed)
        if not steps:
            return
        nb = needs_brew(steps)
        if nb and not self.brew_present and not self._brew_declined:
            self._pending_op = op
            self._brew_names = nb
            self.push_screen(scr.BrewNoticeScreen(nb))
            return
        self._exec_steps(op, steps)

    def _exec_steps(self, op, steps):
        self.mode = None  # the run starts: back to browse mode when the list comes back
        self._redraw_main()
        if any(s.name == SELF_NAME for s in steps) and len(steps) > 1 and self.execv is not None:
            # B8 (changed): the self-update runs through the SAME live worker; only if
            # it ends ok does the process relaunch for the rest of the steps
            self._relaunch_rest = (op, [s for s in steps if s.name != SELF_NAME])
            self._start_run(op, [s for s in steps if s.name == SELF_NAME])
            return
        self._start_run(op, steps)

    @property
    def run_active(self) -> bool:
        return self.run_state is not None

    def _start_run(self, op, steps):
        try:
            timeout = step_timeout_from_env()
        except ValueError as exc:
            self.notify(str(exc), severity="error")  # invalid override: refuse to run
            return
        self._run_op = op
        control = RunControl()
        self._run_control = control
        self.run_state = RunState(op=op, steps=list(steps), started=time.monotonic())
        self._redraw_main()  # appends the gap + dim runstatus options, paints decorations
        self._run_worker(op, steps, control, timeout)

    @work(thread=True, exit_on_error=False, group="run", exclusive=True)
    def _run_worker(self, op, steps, control, timeout):
        state = self.run_state

        def on_event(e):
            if e[0] == "output":
                if state is not None:
                    state.note_output(e[2])  # no call_from_thread per line (R2)
            else:
                self.call_from_thread(self._on_run_event, e)

        results, error = [], None
        try:
            results = self.runner(steps, on_event=on_event, control=control, timeout=timeout,
                                  rows=list(self.rows), reread_one=self.reread_one)
        except Exception as exc:
            error = f"run crashed: {exc}"
        finally:
            try:
                self.call_from_thread(self._finish_run, results, error)
            except RuntimeError:
                pass  # app is shutting down

    def _on_run_event(self, e):
        """UI thread: start/result events update the RunState and repaint one row."""
        state = self.run_state
        if state is None:
            return
        if e[0] == "start":
            state.on_start(e[1], time.monotonic())
            self._repaint_run_row(e[1].name)
            self._scroll_row_into_view(e[1].name)
        elif e[0] == "result":
            state.on_result(e[1])
            self._repaint_run_row(e[1].step.name)

    def _repaint_run_row(self, name):
        screen = self.screen
        if not isinstance(screen, scr.MainScreen):
            return
        ol = screen.query_one("#rows", scr.HoverOptionList)
        ids = [o.id for o in ol.options]
        if name not in ids:
            return
        r = next((r for r in self.rows if r.name == name), None)
        if r is None:
            return
        state = self.run_state
        deco = (state.row_decoration(r, screen._frame, time.monotonic(), screen._frames)
                if state is not None else None)
        ol.replace_option_prompt_at_index(
            ids.index(name),
            scr.row_label(r, r.name in self.ticks, self.mode,
                          self.eligible(r) if self.mode else True, deco=deco))

    def _scroll_row_into_view(self, name):
        screen = self.screen
        if not isinstance(screen, scr.MainScreen):
            return
        ol = screen.query_one("#rows", scr.HoverOptionList)
        ids = [o.id for o in ol.options]
        if name not in ids:
            return
        idx = ids.index(name)
        # ol._lines is private in Textual 3.7.1 — pinned by test_running_row_scrolled_into_view,
        # so a Textual bump that changes it goes RED instead of silent. _lines is indexed by
        # scroll_offset.y + screen_y, so the option's first content line is its POSITION in
        # _lines (not the per-option offset). If Textual ever ships a public
        # get_option_screen_position-style API, switch to it here.
        y = next((pos for pos, (i, _off) in enumerate(ol._lines) if i == idx), None)
        if y is None:
            return
        region = ol.scrollable_content_region
        top = ol.scroll_offset.y
        if not (top <= y < top + region.height):
            ol.scroll_to_region(Region(0, y, 1, 1), animate=False)  # never moves highlighted

    def _finish_run(self, results, error):
        """UI thread, from the worker's finally: unlock, apply after_rows, report."""
        state = self.run_state
        if state is not None:
            state.finished = True
        self.run_state = None
        self._run_control = None
        for res in results:
            after = getattr(res, "after_row", None)
            if after is not None:
                for i, r in enumerate(self.rows):
                    if r.name == res.step.name:
                        self.rows[i] = after
                        break
        carried = self._carried_results or []
        all_results = carried + list(results)
        relaunch = self._relaunch_rest
        self._relaunch_rest = None
        if relaunch is not None:
            op, rest = relaunch
            if not error and results and all(r.ok for r in results):
                # the self-update landed: relaunch for the rest, no report (B8)
                self._redraw_main()
                self.refresh_buttons()
                self.refresh_summary()
                relaunch_with_pending(op, rest, self.pending_path, self.execv)
                return
            # the new code never landed: keep the self ✗ and run the rest inline here
            self._carried_results = all_results
            self._redraw_main()
            self.refresh_buttons()
            self.refresh_summary()
            self._start_run(op, rest)
            return
        self._carried_results = None
        cancel_types = tuple(t for t in (getattr(scr, "CancelConfirmScreen", None),
                                         getattr(scr, "CancelModeScreen", None))
                             if t is not None)
        if cancel_types and isinstance(self.screen, cancel_types):
            self.pop_screen()
        self._redraw_main()
        self.refresh_buttons()
        self.refresh_summary()
        self.push_screen(scr.RunReportScreen(self._run_op, all_results, error))
        self._refresh_worker()  # full background check; nothing network-bound on this thread
