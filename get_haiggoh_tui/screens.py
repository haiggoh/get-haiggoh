"""get_haiggoh_tui.screens — MainScreen and the modal screens (Textual).

Task 7 of docs/superpowers/plans/2026-11-08-tui-01-get-haiggoh-tui.md.
The #info frame and the hover-following option list are PORTED from CSL
(free-agents/bin/session_picker.py:801 and :586 — comments name the source lines).
"""
from __future__ import annotations

import subprocess

from textual import on
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Input, OptionList, Static
from textual.widgets.option_list import Option

from .brew_gate import BUTTONS, INSTALL_ARGV, decline_lines, notice_text
from .menuspec import actions_with_back, build_argv
from .routes import SELF_NAME


class HoverOptionList(OptionList):
    """OptionList that reports which row the mouse is over, so the info box follows the
    pointer as well as the keyboard highlight.
    PORTED from free-agents/bin/session_picker.py:586 (HoverOptionList)."""

    class Hovered(Message):
        def __init__(self, index: int | None):
            super().__init__()
            self.index = index

    def _on_mouse_move(self, event):
        before = self._mouse_hovering_over
        super()._on_mouse_move(event)
        if self._mouse_hovering_over != before:
            self.post_message(self.Hovered(self._mouse_hovering_over))


def row_label(r, ticked: bool) -> str:
    box = "[x]" if ticked else "[ ]"
    status = {"current": "✓", "outdated": r.latest or "",
              "missing": "not installed", "unverified": "? unverified"}[r.status]
    installed = r.installed if r.installed else "—"
    return f"{box} {r.mark} {r.name:<26} {installed:>8}  {status}"


class MainScreen(Screen):
    BINDINGS = [
        Binding("space", "tick", "tick", show=False),
        Binding("a", "all", "all", show=False),
        Binding("n", "none", "none", show=False),
        Binding("u", "update", "update", show=False),
        Binding("i", "install", "install", show=False),
        Binding("x", "uninstall", "uninstall", show=False),
        Binding("q", "quit", "quit", show=False),
    ]

    def compose(self):
        app = self.app
        yield Static("👨🏻‍💻 Get Haiggoh", id="title")
        yield Static("Install and keep every haiggoh plugin up to date", id="subtitle")
        yield Static(app.summary, id="summary")
        yield HoverOptionList(id="rows")
        yield Static("", id="info")
        with Horizontal(id="buttons"):
            yield Button("Select all", id="btn-all")
            yield Button("Unselect all", id="btn-none")
            yield Button("Update 0", id="btn-update")
            yield Button("Install 0", id="btn-install")
            yield Button("Uninstall", id="btn-uninstall")
        yield Static("space tick · enter open · a all · n none · u update · i install · "
                     "x uninstall · q quit", id="hint")

    def on_mount(self):
        self.rebuild_rows()
        self.app.refresh_buttons()

    def rebuild_rows(self):
        ol = self.query_one("#rows", HoverOptionList)
        ol.clear_options()
        options = []
        seen_sections = set()
        for r in self.app.rows:
            if r.section not in seen_sections:
                seen_sections.add(r.section)
                title = "Claude Code plugins" if r.section == "plugin" else "Related tools"
                options.append(Option(title, id=f"section:{r.section}", disabled=True))
            options.append(Option(row_label(r, r.name in self.app.ticks), id=r.name))
        ol.add_options(options)
        if ol.option_count:
            ol.highlighted = 0

    def _row_at(self, index):
        if index is None:
            return None
        ol = self.query_one("#rows", HoverOptionList)
        if index < 0 or index >= ol.option_count:
            return None
        oid = ol.get_option_at_index(index).id
        if not oid or oid.startswith("section:"):
            return None
        return next((r for r in self.app.rows if r.name == oid), None)

    def on_option_list_option_highlighted(self, event):
        # info box follows the KEYBOARD highlight (CSL pattern, session_picker.py:586)
        if event.option_list.id != "rows":
            return
        row = self._row_at(event.option_index)
        if row:
            self.app.show_info_for(row.name)

    def on_hover_option_list_hovered(self, event):
        # …and the MOUSE hover (HoverOptionList.Hovered posted on mouse move)
        row = self._row_at(event.index)
        if row:
            self.app.show_info_for(row.name)

    def on_option_list_option_selected(self, event):
        # the focused OptionList owns the enter key (its "select" binding), so "open"
        # arrives here as OptionSelected on #rows
        if event.option_list.id != "rows":
            return
        self.action_open()

    def action_tick(self):
        row = self._row_at(self.query_one("#rows", HoverOptionList).highlighted)
        if row:
            if row.name in self.app.ticks:
                self.app.ticks.discard(row.name)
            else:
                self.app.ticks.add(row.name)
            self.rebuild_rows()
            self.app.refresh_buttons()

    def action_all(self):
        self.app.ticks = {r.name for r in self.app.rows}
        self.rebuild_rows()
        self.app.refresh_buttons()

    def action_none(self):
        self.app.ticks = set()
        self.rebuild_rows()
        self.app.refresh_buttons()

    def action_update(self):
        self.app.run_op("update")

    def action_install(self):
        self.app.run_op("install")

    def action_uninstall(self):
        app = self.app
        if app.ticks == {SELF_NAME}:
            app.push_screen(SelfUninstallWarning())
            return
        app.push_screen(ConfirmScreen())

    def action_open(self):
        app = self.app
        ol = self.query_one("#rows", HoverOptionList)
        idx = ol.highlighted
        row = self._row_at(idx)
        if not row:
            self.query_one("#info").focus()
            return
        kind, payload = app.menu_for(row)
        if kind == "spec":
            app.push_screen(ItemMenuScreen(row, payload))
        elif kind == "legacy":
            with app.suspend_fn():
                if app.legacy_runner is not None:
                    app.legacy_runner(list(payload))
                else:
                    subprocess.run(list(payload), check=False)
            ol.highlighted = idx  # return to the same highlighted row
        else:
            self.query_one("#info").focus()

    def action_quit(self):
        self.app.exit()

    @on(Button.Pressed, "#btn-all")
    def _b_all(self):
        self.action_all()

    @on(Button.Pressed, "#btn-none")
    def _b_none(self):
        self.action_none()

    @on(Button.Pressed, "#btn-update")
    def _b_update(self):
        self.app.run_op("update")

    @on(Button.Pressed, "#btn-install")
    def _b_install(self):
        self.app.run_op("install")

    @on(Button.Pressed, "#btn-uninstall")
    def _b_uninstall(self):
        self.action_uninstall()


class ConfirmScreen(ModalScreen):
    """Uninstall confirm: lists every ticked installed item and what removing it takes away."""

    BINDINGS = [Binding("enter", "confirm", "confirm", show=False),
                Binding("escape", "dismiss", "cancel", show=False)]

    def __init__(self):
        super().__init__()
        app = self.app
        lines = ["Uninstall these? You can reinstall them from the haiggoh marketplace.", ""]
        for r in app.rows:
            if r.name in app.ticks and r.status in ("current", "outdated", "unverified"):
                lines.append(f"{r.mark} {r.name} — Adds: {r.adds}")
        self.confirm_text = "\n".join(lines)

    def compose(self):
        yield Static(self.confirm_text, id="confirm-text")
        with Horizontal(id="buttons"):
            yield Button("Uninstall", id="btn-confirm")
            yield Button("Cancel", id="btn-cancel")

    def action_confirm(self):
        self.dismiss()
        self.app.run_op("uninstall")

    def action_dismiss(self):
        self.dismiss()

    @on(Button.Pressed, "#btn-confirm")
    def _c(self):
        self.action_confirm()

    @on(Button.Pressed, "#btn-cancel")
    def _x(self):
        self.dismiss()


class SelfUninstallWarning(ModalScreen):
    warning_text = ("Uninstalling Get Haiggoh removes this manager — you can reinstall it "
                    "from the haiggoh marketplace.")

    BINDINGS = [Binding("enter", "confirm", "confirm", show=False),
                Binding("escape", "dismiss", "cancel", show=False)]

    def compose(self):
        yield Static(self.warning_text, id="warning")
        with Horizontal(id="buttons"):
            yield Button("Uninstall anyway", id="btn-confirm")
            yield Button("Cancel", id="btn-cancel")

    def action_confirm(self):
        self.dismiss()
        self.app.ticks = {SELF_NAME}
        self.app.run_op("uninstall")

    def action_dismiss(self):
        self.dismiss()

    @on(Button.Pressed, "#btn-confirm")
    def _c(self):
        self.action_confirm()

    @on(Button.Pressed, "#btn-cancel")
    def _x(self):
        self.dismiss()


class BrewNoticeScreen(ModalScreen):
    """The 🍺 Homebrew moment: honest notice, two buttons. The installer ALWAYS runs
    under App.suspend() (it needs the real terminal for the password) and
    verify_installed() decides what happens next — never assumed."""

    BINDINGS = [Binding("enter", "install_brew", "install", show=False),
                Binding("c", "decline", "continue without", show=False)]

    def __init__(self, names):
        super().__init__()
        self.names = list(names)
        self.notice = notice_text(self.names)

    def compose(self):
        yield Static(self.notice, id="notice")
        with Horizontal(id="buttons"):
            yield Button(BUTTONS[0], id="btn-install-brew")
            yield Button(BUTTONS[1], id="btn-continue")

    def action_install_brew(self):
        app = self.app
        with app.suspend_fn():
            if app.installer_runner is not None:
                app.installer_runner(INSTALL_ARGV)
            else:
                subprocess.run(INSTALL_ARGV, check=False)
        if app.verify_installed():
            app.brew_present = True
            self.dismiss()
            app.run_op(app._pending_op)
        else:
            # the installer ran but brew still does not resolve: decline path, not success
            app.decline_lines = decline_lines(app.rows, self.names)
            app._brew_declined = True
            self.dismiss()

    def action_decline(self):
        app = self.app
        app.brew_allowed = False
        app._brew_declined = True
        app.decline_lines = decline_lines(app.rows, self.names)
        self.dismiss()
        app.run_op(app._pending_op)

    @on(Button.Pressed, "#btn-install-brew")
    def _i(self):
        self.action_install_brew()

    @on(Button.Pressed, "#btn-continue")
    def _c(self):
        self.action_decline()


class ProgressScreen(ModalScreen):
    """Runs the planned steps via the injectable runner and lists failures with their
    output; the final state is re-read from disk (the runner decides ok), never from
    exit codes."""

    def __init__(self, op, steps):
        super().__init__()
        self.op = op
        self.steps = list(steps)

    def compose(self):
        yield Static(f"Running {self.op}…", id="progress-title")
        yield Static("", id="progress-out")
        yield Button("Done", id="btn-done")

    def on_mount(self):
        app = self.app
        results = app.runner(self.steps)
        lines = []
        for res in results:
            mark = "✓" if res.ok else "✗"
            lines.append(f"{mark} {res.step.name} ({res.step.route})")
            if not res.ok and res.output:
                lines.append("    " + res.output.strip().splitlines()[0][:100] if res.output.strip() else "")
        self.query_one("#progress-out", Static).update("\n".join(lines))
        app.refresh_after_run()

    @on(Button.Pressed, "#btn-done")
    def _d(self):
        self.dismiss()


class ItemMenuScreen(ModalScreen):
    """A menu-spec overlay: renders the item's declared actions (Back LAST), asks each
    prompt as a dialog, builds argv from the answers (never shell-joined), shows panel
    output in a panel or hands the terminal over for output: terminal."""

    BINDINGS = [Binding("escape", "dismiss", "back", show=False)]

    def __init__(self, row, spec):
        super().__init__()
        self.row = row
        self.spec = spec
        self.actions = actions_with_back(spec)

    def compose(self):
        yield Static(self.spec.get("title", self.row.name), id="menu-title")
        yield OptionList(id="menu-actions")
        yield Static("", id="menu-out")

    def on_mount(self):
        ol = self.query_one("#menu-actions", OptionList)
        ol.add_options([Option(a.get("label", "?"), id=f"act:{i}")
                        for i, a in enumerate(self.actions)])

    def on_option_list_option_selected(self, event):
        if event.option_list.id != "menu-actions":
            return
        i = int(str(event.option.id).split(":", 1)[1])
        action = self.actions[i]
        if action.get("label") == "👨🏻‍💻 Back to Get Haiggoh":
            self.dismiss()
            return
        answers = {}
        prompts = action.get("prompts") or []
        if prompts:
            self.app.push_screen(PromptDialog(action, prompts, answers, on_done=self._run_action))
        else:
            self._run_action(action, answers)

    def _run_action(self, action, answers):
        argv = build_argv(action, answers)
        if action.get("output") == "terminal":
            with self.app.suspend_fn():
                subprocess.run(argv, check=False)
            return
        r = subprocess.run(argv, capture_output=True, text=True)
        self.query_one("#menu-out", Static).update((r.stdout or "") + (r.stderr or ""))


class PromptDialog(ModalScreen):
    def __init__(self, action, prompts, answers, on_done):
        super().__init__()
        self.action = action
        self.prompts = list(prompts)
        self.answers = answers
        self.on_done = on_done

    def compose(self):
        p = self.prompts[0]
        yield Static(p.get("question", ""), id="q")
        if p.get("type") == "choice":
            yield OptionList(id="choices")
        else:
            yield Input(value=p.get("default") or "", id="answer")
        yield Button("OK", id="btn-ok")

    def on_mount(self):
        p = self.prompts[0]
        if p.get("type") == "choice":
            ol = self.query_one("#choices", OptionList)
            ol.add_options([Option(c.get("label", c.get("value", "?")), id=c.get("value", "?"))
                            for c in (p.get("choices") or [])])

    def _submit(self):
        p = self.prompts[0]
        if p.get("type") == "choice":
            ol = self.query_one("#choices", OptionList)
            idx = ol.highlighted
            choice = (p.get("choices") or [])[idx]
            self.answers[p["id"]] = choice.get("value", "")
        else:
            self.answers[p["id"]] = self.query_one("#answer", Input).value
        rest = self.prompts[1:]
        if rest:
            self.app.push_screen(PromptDialog(self.action, rest, self.answers, self.on_done))
            self.dismiss()
        else:
            self.dismiss()
            self.on_done(self.action, self.answers)

    @on(Button.Pressed, "#btn-ok")
    def _ok(self):
        self._submit()

    @on(Input.Submitted, "#answer")
    def _sub(self):
        self._submit()


class ResumeScreen(ModalScreen):
    """A leftover pending file from a crash is offered for resume — never silently replayed."""

    BINDINGS = [Binding("r", "resume", "resume", show=False),
                Binding("d", "discard", "discard", show=False)]

    def __init__(self, pending):
        super().__init__()
        self.pending = pending

    def compose(self):
        yield Static("A previous bulk run was interrupted. Resume it?", id="resume-q")
        with Horizontal(id="buttons"):
            yield Button("Resume", id="btn-resume")
            yield Button("Discard", id="btn-discard")

    def action_resume(self):
        from .runner import consume_pending
        data = consume_pending(self.app.pending_path) or self.pending
        self.dismiss()
        self.app.ticks = set(data.get("names") or [])
        self.app.run_op(data.get("op", "update"))

    def action_discard(self):
        from .runner import clear_pending
        clear_pending(self.app.pending_path)
        self.dismiss()

    @on(Button.Pressed, "#btn-resume")
    def _r(self):
        self.action_resume()

    @on(Button.Pressed, "#btn-discard")
    def _d(self):
        self.action_discard()
