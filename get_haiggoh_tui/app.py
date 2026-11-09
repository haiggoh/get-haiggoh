"""get_haiggoh_tui.app — the Textual app (the ONLY module besides screens.py that imports Textual).

Task 7 of docs/superpowers/plans/2026-11-08-tui-01-get-haiggoh-tui.md. Collaborators are
injectable (rows_loader, runner, menu_for, legacy_runner, installer_runner,
verify_installed, execv) so pilot tests never touch real claude/brew/network.
Paint comes from rows_loader(cached=True); a worker refreshes with cached=False.
"""
from __future__ import annotations

import os
from pathlib import Path

from textual import work
from textual.app import App

from . import screens as scr
from .brew_gate import needs_brew
from .inventory import Row
from .menuspec import menu_for
from .routes import SELF_NAME, brew_path, plan_steps
from .runner import consume_pending, read_pending, run_steps, self_update_then_relaunch
from .selection import default_ticks, is_first_run, mark_first_run_done
from .status import build_rows


def _state_path() -> Path:
    return Path(os.environ.get("GET_HAIGGOH_TUI_STATE_FILE")
                or "~/.claude/.get-haiggoh-tui-state.json").expanduser()


def _pending_path() -> Path:
    return Path(os.environ.get("GET_HAIGGOH_TUI_PENDING_FILE")
                or "~/.claude/.get-haiggoh-tui-pending.json").expanduser()


_STATUS_TEXT = {"current": "✓", "missing": "not installed", "unverified": "? unverified"}


class GetHaiggohApp(App):
    """CSL-style TUI listing every haiggoh plugin and related tool."""

    CSS_PATH = "theme.tcss"

    def __init__(self, rows_loader=build_rows, runner=run_steps, state_path=None,
                 pending_path=None, brew_present=None, resume=False, menu_for=menu_for,
                 legacy_runner=None, installer_runner=None, verify_installed=None,
                 execv=None, suspend_fn=None):
        super().__init__()
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
        self.rows: list[Row] = []
        self.ticks: set[str] = set()
        self.summary = ""
        self.decline_lines: list[str] = []
        self.refresh_failed = False
        self._info_name: str | None = None
        self._pending_op = "update"

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
        first = is_first_run(self.state_path)
        self.ticks = default_ticks(self.rows, first)
        mark_first_run_done(self.state_path)  # after the first paint
        self.refresh_summary()
        self.push_screen(scr.MainScreen())
        self._refresh_worker()

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

    def refresh_after_run(self):
        """Re-read rows from disk after a run (the runner's ok already came from state)."""
        try:
            self._apply_rows(list(self.rows_loader(False)))
        except Exception:
            pass

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
            screen.query_one("#info", Static).update(self.info_text())

    def info_text(self) -> str:
        r = next((x for x in self.rows if x.name == self._info_name), None)
        if not r:
            return ""
        status = _STATUS_TEXT.get(r.status) or f"latest {r.latest}"
        lines = [f"{r.mark} {r.name} — installed {r.installed or 'not installed'} {status}",
                 r.description, f"Adds: {r.adds}"]
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
        up = sum(1 for r in self.rows if r.name in self.ticks and r.status == "outdated")
        ins = sum(1 for r in self.rows if r.name in self.ticks and r.status == "missing")
        screen.query_one("#btn-update").label = f"Update {up}"
        screen.query_one("#btn-install").label = f"Install {ins}"

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
        if any(s.name == SELF_NAME for s in steps) and len(steps) > 1 and self.execv is not None:
            self_update_then_relaunch(steps, self.pending_path, execv=self.execv)
            return
        self.push_screen(scr.ProgressScreen(op, steps))
