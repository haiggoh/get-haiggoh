# get-haiggoh TUI — live, non-blocking bulk-run progress — design

Date: 2026-11-23 · Status: draft for review · Branch: `feat/tui-live-run-progress` (worktree `.wt/tui-live-run-progress`)

## Intent — why this exists

User story (2026-11-23, verbatim symptom): in the TUI's update mode, Select all, Update — with
only ONE outdated item (transcript-distiller) the app looked completely frozen: no spinner, no
progress, no hover reaction, no click response, for an unacceptably long time. The user almost
force-quit, believing the app was wedged. With several items it is worse: nothing shows which
item is running or how far the queue is.

Root cause (verified in source): `ProgressScreen.on_mount` (get_haiggoh_tui/screens.py:490-500)
calls `app.runner(self.steps)` **synchronously on the UI thread**, and `run_steps`
(runner.py:111-142) executes each step with blocking `subprocess.run(..., capture_output=True)`
— so no repaint, no input, and no output until every step has finished. The runner already emits
`on_event(("start", step))` / `(("result", result))` but the default consumer ignores them.

## Goals

1. A bulk run (update / install / uninstall — all three share the same machinery) executes on a
   Textual worker thread. The main list stays painted and fully interactive for the whole run:
   hover still moves the info box, keys still work, buttons still respond. No modal lockout.
2. The currently-executing item's **own row** carries a spinner and a progress bar right after
   the item name (user requirement).
3. **Below the "Q) Quit" action row — separated by one blank row** — a dim, self-refreshing line
   shows the live verbose line of what is happening in the background (user requirement).
4. Each item's row flips to `✓ <new version>` / `✗` the moment its step finishes; `ok` still
   comes from the runner's state re-read, never from the exit code.
5. After the run, a closing **report modal** lists every item with ✓/✗ and the first error line
   of each failure (hybrid presentation, user-chosen).
6. Cancel UX (user-specified): first `Esc` during a run opens a confirm dialog "Cancel the run?
   y/n". On yes, a second dialog asks "Finish current item, then stop" OR "Cancel and stop
   immediately". **Two `Esc` presses in quick succession (≤ 0.5 s) mean immediate cancel+stop**
   and skip the dialogs.
7. Even when the running command prints nothing, the dim line shows a heartbeat
   (`▸ <command> · 0:14 · pulse`) so silence never reads as wedged.
8. A per-step timeout watchdog (default 600 s, env `GET_HAIGGOH_STEP_TIMEOUT`) turns a hung
   subprocess into `✗ timed out` and the queue continues.

## The running state (mockup)

```
👨🏻‍💻 Get Haiggoh
⬆️ Update — item 2 of 5 · 0:41            ← subtitle carries overall progress + elapsed

  Claude Code plugins
🧭 waypoints            0.15.0  ✓ updated
📦 transcript-distiller ⠋ ▐████░░░░░░ 0.8.0 → 0.9.1   ← running row: spinner + bar after the name
💸 cost-tracker         —       not installed
…
  Q) Quit
                                            ← one blank gap row (not directly below Quit)
  ▸ claude plugin update transcript-distiller@haiggoh · step 1/1 · 0:14 · ▓ alive   ← dim line
```

After the run ends, the report modal:

```
╭─ ⬆️ Update report — 4 ok · 1 failed ─╮
│ ✓ waypoints (plugin)                 │
│ ✗ human-shell — brew: command not…  │
│         [ Done ]                     │
╰──────────────────────────────────────╯
```

## Decisions — as decided with the user, 2026-11-23

| # | Decision | Choice |
|---|----------|--------|
| D1 | Presentation during the run | Inline on the main list (no modal), plus a closing report modal = **hybrid** (over inline-only and live-modal-only) |
| D2 | Bar meaning | Per-item sub-steps (a row can have a plugin step + a brew step → 1/2, 2/2); overall "n of N" lives in the dim line and subtitle |
| D3 | Dim line when the command prints nothing | Heartbeat: running command + elapsed + animated pulse |
| D4 | Cancel | Esc → "Cancel the run? y/n" → "finish current item then stop" / "cancel and stop immediately"; double-Esc (≤0.5 s) = immediate |
| D5 | Dim line position | Inside the `#rows` OptionList, after `action:quit`, with one blank gap row between (user: "spaced, not directly the next row") |
| D6 | Scope | update, install AND uninstall (same run path; user explicitly cares about multi-install) |

## Builder's calls (declared, not user-decided)

- B1. Spinner glyphs: braille frames `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏` (macOS terminals are UTF-8; the app already requires
  a modern terminal); ASCII fallback `|/\-` only if `LC_ALL`/locale is C/POSIX.
- B2. Repaint cadence: one 150 ms interval timer in MainScreen repaints the spinner frame, the
  bar, the elapsed clock and the pulse — even with zero new output (that IS the heartbeat).
- B3. Dim line is clamped to terminal width, single line, trailing `…` — it must never wrap or
  reflow the list mid-run.
- B4. Bar width: 10 cells, `▐` + `█`×done + `░`×rest; fraction = steps of THIS item done/total.
- B5. During a run, `q` does NOT quit (would orphan the subprocess); it notifies
  "run in progress — esc to cancel". Ticking / mode keys / run buttons are inert during a run;
  only navigation, hover, Esc-cancel work.
- B6. Timeout: `GET_HAIGGOH_STEP_TIMEOUT` in seconds (float ok); `<= 0` disables; an invalid value
  falls back to 600 s and says so in the dim line (loud, never silent).
- B7. "Cancel and stop immediately" kills the in-flight process group. The dialog names the risk
  (half-updated plugin / brew lock). The report marks the item `✗ cancelled` and the rest
  `skipped`.
- B8. The self-update resume path (`self_update_then_relaunch` → execv `--resume`) is unchanged;
  the resumed run goes through the same inline UI.
- B9. Row animation uses `OptionList.replace_option_prompt_at_index` (verified present in the
  pinned Textual 3.7.1) so the spinner/dim line update in place — `clear_options`+`add_options`
  would reset highlight and scroll every frame.

## Non-goals

- No byte/percent progress claims from tools that do not report it; no fabricated phases.
- No parallel/concurrent steps (brew takes a lock; `claude plugin` mutates shared state) — sequential only.
- No changes to `plan_steps` routing, status detection, the pending/resume file format, or the
  pre-run brew gate (`BrewNoticeScreen` stays as-is).
- No real subprocesses, network, brew or `claude` calls in tests — the injectable seams stay.

## Anti-goals — failure even if it technically works

- A silent wait: any interval longer than ~1 s with zero visible change while a command runs.
- A dim line that wraps or reflows the list.
- Killing a command without an explicit user choice (the immediate path must be a deliberate dialog/double-Esc).
- A test suite that passes while the UI is still blocking (green-but-inert).

## Risks

- R1. Immediate cancel can leave a half-updated plugin or a stale brew lock → mitigated by B7
  (explicit dialog wording, report marks it); the resume pending-file is only written by the
  self-update path and is untouched by cancel.
- R2. Event storm from a chatty command flooding the UI thread → the worker coalesces output
  lines; the UI only ever keeps the LAST line for the dim line and repaints at 150 ms max.
- R3. The background refresh worker (`_refresh_worker`) completing mid-run calls
  `rebuild_rows()` → row decoration must be a pure function of `app.run_state`, so a rebuild
  re-derives it instead of wiping it.
- R4. `execv` relaunch (self-update first step) replaces the process mid-run — unchanged
  behaviour, but the pending resume must land on the new inline UI (B8).

## How (surface, left to the plan)

- `runner.py`: streaming executor (Popen, line-read, emits `("output", step, line)`) behind the
  existing injectable `execute` seam; `on_event` gains `("output", step, line)`; per-step
  timeout via a read deadline + process-group kill; a stop handle (`after_current` /
  `immediate`) checked between steps; `run_steps` signature and ok-from-re-read semantics stay
  so existing tests stay green.
- `app.py`: a `RunState` dataclass on the app; a `@work(thread=True)` run worker bridging events
  with `call_from_thread`; cancel dialogs; after the worker finishes → `refresh_after_run()` +
  report screen; run buttons/mode locked while `run_state` is active.
- `screens.py`: `row_label()` gains run decorations from `run_state`; `#rows` gains a gap
  option + a dim `runstatus` option after `action:quit` while running; the 150 ms timer; the
  two cancel dialogs; `RunReportScreen` replaces `ProgressScreen`'s report role (the blocking
  modal goes away).
- `theme.tcss`: dim style for the run-status option (`ansi_bright_black`, matching `#summary`).
- Tests: runner unit tests (event order, streaming, timeout, both cancel modes, existing
  semantics untouched) + pilot tests with a controllable fake runner (spinner+bar in the running
  row, dim line below a gap under Quit, input still handled mid-run, Esc/double-Esc flows, report
  modal contents) + known-bad mutations (make the run synchronous → responsiveness test goes
  red; drop the dim line → its test goes red).
- Version/release: 0.10.6 → **0.11.0** (minor, new feature); bump every version surface
  (`.claude-plugin/plugin.json`, CHANGELOG top entry, `portable/` manifest + PORTABLE-BUILD.json
  if they carry the version, README/--help if they print it); ship via the repo's `rtc-ship`
  from the worktree, then refresh the installed plugin and dogfood a real update.
