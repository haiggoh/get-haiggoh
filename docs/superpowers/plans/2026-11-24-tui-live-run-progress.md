# get-haiggoh TUI — live, non-blocking bulk-run progress — Implementation Plan

**Status:** draft

> **Lasting Plans:** when every task below is done, set the Status line to `completed` by running `lasting-plans complete "docs/superpowers/plans/2026-11-24-tui-live-run-progress.md"` as the closing step.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (NATIVE execution: you implement every task yourself, then one final whole-branch review). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A bulk update / install / uninstall runs on a worker thread while the main list stays live: spinner + per-item bar on the running row, a dim heartbeat line under `Q) Quit`, ✓/✗ per row as steps land, Esc-cancel dialogs, a per-step timeout, and a closing report modal.

**Architecture:** `runner.py` gains a streaming, killable executor (`stream_execute`) and a `RunControl` stop handle behind the existing `run_steps` seam. A new pure module `runstate.py` (no Textual) holds the run model and every string the UI paints (spinner, bar, row decoration, dim line, subtitle), so rendering is unit-testable. `app.py` runs `run_steps` in a `@work(thread=True)` worker and bridges events with `call_from_thread`; `screens.py` paints from `app.run_state` on a 150 ms timer, adds the cancel dialogs and `RunReportScreen`, and deletes the blocking `ProgressScreen`.

**Tech Stack:** Python 3 stdlib (runner/runstate), Textual 3.7.1 (pinned, TUI venv `~/.local/share/get-haiggoh/tui-venv`), pytest 9.

**Spec:** `docs/superpowers/specs/2026-11-23-get-haiggoh-tui-live-run-progress-design.md` (commit `7f46276`). Read it in full before Task 1; decisions D1–D6 and builder calls B1–B9 are binding except where this plan's "Deviations" says otherwise.

## 🚨 System instructions for the executor — read first

1. This plan is self-contained; do not depend on any previous chat. Revalidate every "confirmed live" fact in Phase 0 before the first edit.
2. Work ONLY in the worktree `~/ClaudeWorkspace/get-haiggoh/.wt/tui-live-run-progress` on branch `feat/tui-live-run-progress`. NEVER switch the branch of the canonical checkout `~/ClaudeWorkspace/get-haiggoh` (launchers resolve through it) and never edit `~/.claude/plugins/cache/**` (a derived copy; the next update silently reverts it).
3. Output exactly three strategy sentences before the first file edit, then run Phase 0.
4. Use the native Read/Edit/Write tools for files; the shell for git, tests and execution. Edit anchors come from a FRESH Read, whole lines, exact indentation. Never rewrite a file from a partial view.
5. Stage BY PATH (`git add <paths>`), never `git add -A` / `.`; check `git diff --cached --stat` before each commit. Commit messages end with the session's attribution trailer.
6. Pilot tests run ONLY under the TUI venv python: `~/.local/share/get-haiggoh/tui-venv/bin/python -m pytest … -rs`. A skipped pilot test is a FAILED receipt, never a pass.
7. Every task ends with its 🧪 Receipt: the command, its pass line / exit code quoted verbatim, and the discriminant (the mutation that went RED). Failure ⇒ STOP that task, diagnose, fix, rerun, show both runs.
8. Respect the authority matrix. **Highest boundary granted by this plan: push of the feature branch.** Merge, tag, release, plugin refresh need the user's separate explicit go (Task 9 asks for it).
9. No real `claude`, `brew`, `git clone` or network calls in tests. Short-lived `sys.executable -c` children are allowed ONLY in `tests/tui/test_stream_exec.py` (see Deviations).
10. No secrets in receipts.

## 📌 Context and objectives

**Current → required behaviour** (entry point: `bin/get-haiggoh-tui` → `GetHaiggohApp`; state: `app.run_state`):

| Situation | Now | Required |
|---|---|---|
| Update/Install/Uninstall pressed | `ProgressScreen.on_mount` runs `app.runner(steps)` on the UI thread — frozen, no output | runner on a worker thread; list painted + interactive throughout |
| Running item | nothing | its row: `⠋ ▐████░░░░░░ 0.8.0 → 0.9.1` right after the name |
| Background activity | nothing | dim line one gap row under `Q) Quit`, refreshed every 150 ms, heartbeat when silent |
| Step finishes | nothing until all finish | row flips to `✓ <new version>` / `✗ <reason>` at once |
| Run ends | modal list | `RunReportScreen` (✓/✗, first error line) |
| Hung command | hangs forever | `✗ timed out` after `GET_HAIGGOH_STEP_TIMEOUT` (default 600 s), queue continues |
| Esc during run | n/a | confirm → finish-current / immediate; double-Esc ≤ 0.5 s = immediate |

**Evidence (labelled):**
- *confirmed live 2026-11-24:* worktree clean at `7f46276`, contains `origin/main` (`a4a0763`); canonical checkout on `main`.
- *confirmed live 2026-11-24:* TUI venv has Textual 3.7.1 + pytest 9.2.0, **no pytest-xdist**; `~/.local/bin/pytest` (pipx) has xdist but **cannot import textual**.
- *confirmed live 2026-11-24:* `rtc-ship.json` has no `test_cmd`, so `rtc-ship` runs `~/.local/bin/pytest -q tests` ⇒ **every pilot test is importorskip'd at ship time** (pre-existing gap; Task 1 closes it).
- *confirmed live 2026-11-24:* version surfaces = `.claude-plugin/plugin.json` (0.10.6), `portable/.claude-plugin/plugin.json` (0.10.6, GENERATED by `scripts/build-portable.py`, freshness-tested by `tests/test_portable.py`), `CHANGELOG.md`. `PORTABLE-BUILD.json` carries no version.
- *dated 2026-11-23 (builder-check):* `run_steps` / `ProgressScreen` / `self_update_then_relaunch` have no consumers outside `runner.py`, `app.py`, `screens.py` and `tests/tui/`.
- *dated 2026-11-23:* `OptionList.replace_option_prompt_at_index` exists in Textual 3.7.1.
- *unknown to inspect (Phase 0):* whether README describes the run screen (`grep -n -i 'progress\|running' README.md`).

**Deviations from the spec (decisions, with reason):**
- **B6 changed:** an INVALID `GET_HAIGGOH_STEP_TIMEOUT` (set but not a number) makes the run refuse to start with an error notification naming the variable and its value — it does NOT fall back to 600 s. Reason: the user's standing rule "explicit overrides fail loudly — never fall through to the default". Unset ⇒ 600; `<= 0` ⇒ disabled (as spec).
- **Non-goal "no real subprocesses in tests" interpreted:** its intent is no side effects (no claude/brew/network). The streaming executor's kill/timeout behaviour can only be proven on a real process group, so `test_stream_exec.py` spawns `sys.executable -c` children only. Every other test injects fakes.
- **Gate fix added (Task 1):** not in the spec, but without it the spec's anti-goal "a suite that passes while the UI is still blocking" is guaranteed at ship time.

**Acceptance criteria:** all spec Goals 1–8 observable in pilot tests under the TUI venv with 0 skips; the ship gate runs those pilot tests; mutations listed per task go RED; screenshots of the running state, both cancel dialogs and the report inspected (Task 8); version 0.11.0 on every surface.

## 🔒 Authority matrix

| Operation | Status | Gate / evidence |
|---|---|---|
| Read-only inspection anywhere | allowed now | — |
| Edit files in the worktree; local commits on `feat/tui-live-run-progress` | allowed now | stage by path; receipt per task |
| Edit `rtc-ship.json` (repo config) | allowed now (Task 1) | config-only |
| Install packages into ANY venv (incl. adding xdist to the TUI venv) | prohibited | not needed; ask the user if you believe otherwise |
| `git push origin feat/tui-live-run-progress` | allowed after Task 8 receipt | full gate green, 0 pilot skips |
| Merge to `main`, tag `v0.11.0`, GitHub release, `rtc-ship`, `claude plugin update`, `get-haiggoh apply` | **needs separate user permission** | Task 9 asks; a branch push never implies it |
| Run the real TUI against real plugins (dogfood) | needs user present | Task 9; real `claude plugin update` mutates state |
| Kill processes outside tests' own children; touch `~/.claude` registries | prohibited | — |

## Global Constraints

- Textual stays pinned at 3.7.1; no new runtime dependencies. `runner.py` and `runstate.py` import no Textual (and no `rich` in `runstate.py`).
- Row labels and the dim line are `rich.text.Text` objects, never markup strings (`[x]` is eaten as markup — 0.10.2 bug).
- The UI thread never calls a blocking subprocess. The only exception left is `self_update_then_relaunch` (B8, unchanged on purpose).
- `ok` is still decided by re-read state (`_ok_from_state`), never by an exit code.
- Spinner frames `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`; ASCII `|/-\` only when the effective locale (first non-empty of `LC_ALL`, `LC_CTYPE`, `LANG`) is exactly `C` or `POSIX`.
- Repaint cadence 150 ms; bar 10 cells `▐` + `█`×done + `░`×rest; dim line single line, clamped to the list's content width with trailing `…`.
- Timeout env `GET_HAIGGOH_STEP_TIMEOUT` (seconds, float ok); unset ⇒ 600; `<= 0` ⇒ none; invalid ⇒ refuse to run (Deviation B6).
- Double-Esc window 0.5 s. Version 0.10.6 → **0.11.0**.

## Review Focus

1. **Chatty command** (thousands of lines/s, e.g. `brew upgrade` or git progress) — UI must stay responsive and show only the last line. Pinned: Task 6 `test_flood_of_output_keeps_ui_responsive`.
2. **Messy output** — `\r` progress redraws, ANSI colour codes, no trailing newline, non-UTF-8 bytes — the dim line must show one clean line, never escape junk or a crash. Pinned: Task 3 `test_non_utf8_and_no_newline`, Task 5 `test_note_output_strips_ansi_and_carriage_returns`.
3. **The runner itself fails** — the command is missing (`FileNotFoundError` for `brew`), or `reread` / the runner raises mid-run — the run must end, the report must show ✗ with the reason, and the UI must unlock. Pinned: Task 3 `test_missing_command_is_a_result_not_an_exception`, Task 6 `test_runner_crash_unlocks_and_reports`.
4. **A background refresh lands mid-run** (`_refresh_worker` → `rebuild_rows`) — the decorations must survive (R3). Pinned: Task 6 `test_refresh_mid_run_keeps_decorations`.
5. **Narrow terminal or long names** — the dim line never wraps. Pinned: Task 5 `test_dim_line_clamps_to_width`, Task 6 `test_dim_line_single_line_in_narrow_terminal`.

## Quality-control milestones (playbook: `~/.claude/plans/_PLAYBOOKS/Playbook-milestone-qc-offload-test-proof.md`)

At each milestone, run /offload (free-agents:offload): a stateless dispatch to an out-of-family reviewer with the playbook's brief, attaching the plan task text, the test files, the fixtures and the implementation through `"files"`. Treat its findings as hypotheses: run every proposed mutation; fix or rebut each finding with evidence. Do not start the next task with an open finding. Each milestone also applies `superpowers:verification-before-completion`. Record the model and route in the receipt.

| Milestone | After | Requirements under review | Test files |
|---|---|---|---|
| QC-1 | Task 3 | runner contract: streaming events, stop modes, timeout, process-group kill, ok-from-state unchanged | `test_runner.py`, `test_stream_exec.py` |
| QC-2 | Task 6 | Goals 1–5, 7, B5, R3, Review Focus 1/3/4/5 | `test_runstate.py`, `test_live_run.py` |
| QC-3 | Task 7 | Goal 6 (both dialogs, double-Esc), B7 wording, ctrl+q | `test_live_run_cancel.py` |
| QC-4 | Task 8 | gate really runs the pilots; screenshots match the spec mockups; version surfaces | the gate log, screenshots |

**Test-file layout (split playbook, decided up front):** the waiting cases (real children, 150 ms timers, gated runners) go in their own files — `test_stream_exec.py`, `test_live_run.py`, `test_live_run_cancel.py` — so none of them becomes the floor of `test_app_pilot.py` / `test_tui_0102.py`. Each case uses timeouts ≤ 1 s.

**Free-lane routing (Credit Efficient Mode):** the QC dispatches go to free lanes. Tasks 2, 4 and 5 (pure, fully specified by their tests) may be handed to a free session via free-session-handover; Tasks 6–7 (Textual threading) stay with the main executor.

---

## 🛑 Phase 0 — forced preflight (no edits)

- [ ] **Step 1:** Write three sentences: how Task 1 (the gate) makes every later receipt trustworthy; how Tasks 2–7 deliver Goals 1–8; where the run stops (Task 9's permission gate).
- [ ] **Step 2:** Read-only checks — run and quote:
```bash
cd ~/ClaudeWorkspace/get-haiggoh/.wt/tui-live-run-progress
git status --porcelain; git branch --show-current; git log --oneline -1
git fetch -q origin && git merge-base --is-ancestor origin/main HEAD && echo CONTAINS-MAIN
git -C ~/ClaudeWorkspace/get-haiggoh branch --show-current
~/.local/share/get-haiggoh/tui-venv/bin/python -c "import textual; print(textual.__version__)"
grep -n -i 'progress\|running' README.md
```
Expected: empty status; `feat/tui-live-run-progress`; `CONTAINS-MAIN`; canonical `main`; `3.7.1`. If `origin/main` moved, STOP and ask before rebasing.
- [ ] **Step 3: Baseline.** `pytest -q -n auto tests -p no:cacheprovider > /tmp/gh-base-1.log 2>&1; echo EXIT:$?` then `~/.local/share/get-haiggoh/tui-venv/bin/python -m pytest -q -rs tests/tui -p no:cacheprovider > /tmp/gh-base-2.log 2>&1; echo EXIT:$?`. Quote both summary lines; the second must show 0 skipped. Pre-existing failures ⇒ STOP and report (no release ships around a known red).

🧪 **Receipt 0:** the outputs above, plus the two baseline summary lines.

---

### Task 1: The ship gate runs the pilot tests and refuses skips

**Files:**
- Create: `tests/tui/conftest.py`
- Create: `tests/tui/test_gate_requirement.py`
- Modify: `rtc-ship.json` (add `test_cmd`)

**Interfaces:**
- Produces: `tests/tui/conftest.py::required_violation(env: Mapping[str, str], textual_ok: bool, skipped: int) -> str | None` and the env switch `GET_HAIGGOH_REQUIRE_TEXTUAL=1`.

- [ ] **Step 1: Write the failing tests** in `test_gate_requirement.py` (it imports `conftest` via `from tests.tui.conftest import required_violation`, or via `importlib` from its own directory):
```python
def test_off_by_default(self):
    self.assertIsNone(required_violation({}, textual_ok=False, skipped=5))
def test_required_but_textual_missing(self):
    msg = required_violation({"GET_HAIGGOH_REQUIRE_TEXTUAL": "1"}, textual_ok=False, skipped=0)
    self.assertIn("textual", msg); self.assertIn("GET_HAIGGOH_REQUIRE_TEXTUAL", msg)
def test_required_and_skips_present(self):
    self.assertIn("3 skipped", required_violation({"GET_HAIGGOH_REQUIRE_TEXTUAL": "1"}, True, 3))
def test_required_clean(self):
    self.assertIsNone(required_violation({"GET_HAIGGOH_REQUIRE_TEXTUAL": "1"}, True, 0))
```
- [ ] **Step 2:** Run `python3 -m pytest tests/tui/test_gate_requirement.py -q`; expected FAIL (no `required_violation`).
- [ ] **Step 3: Implement** `required_violation` plus two hooks in `tests/tui/conftest.py`: `pytest_configure(config)` raises `pytest.UsageError(msg)` when the requirement is on and `import textual` fails (the message names `sys.executable`); `pytest_sessionfinish(session, exitstatus)` reads `session.config.pluginmanager.get_plugin("terminalreporter").stats.get("skipped", [])` and, on a violation, prints the message and sets `session.exitstatus = 1`.
- [ ] **Step 4: Add the gate command** to `rtc-ship.json`:
```json
"test_cmd": "pytest -q -n auto tests -p no:cacheprovider && GET_HAIGGOH_REQUIRE_TEXTUAL=1 \"$HOME/.local/share/get-haiggoh/tui-venv/bin/python\" -m pytest -q -rs tests/tui -p no:cacheprovider"
```
(Write it with Edit; JSON-escape the inner quotes. Check how `rtc-ship.sh` evaluates `test_cmd` — `grep -n 'gate_once' -A12` in the installed rtc-ship — and confirm `$HOME` expands there. If it does not, use the form that it does expand and say so in the receipt.)
- [ ] **Step 5:** Run the unit tests (PASS). Then run the `test_cmd` string by hand from the worktree root: `sh -c "<test_cmd>" > /tmp/gh-gate.log 2>&1; echo EXIT:$?`. Expected `EXIT:0`, and the second summary has 0 skipped.
- [ ] **Step 6: Discriminant.** Run `GET_HAIGGOH_REQUIRE_TEXTUAL=1 pytest -q tests/tui/test_app_pilot.py -p no:cacheprovider; echo EXIT:$?` with the pipx pytest (no textual). Expected: non-zero and the message names textual. Then temporarily add `@unittest.skip("x")` to one pilot test, run the venv half: non-zero with "1 skipped"; revert; `git diff --stat` shows no leftover.
- [ ] **Step 7: Commit** `tests/tui/conftest.py tests/tui/test_gate_requirement.py rtc-ship.json` — `test(gate): ship gate runs TUI pilots under the venv and fails on skips`.

🧪 **Receipt 1:** the Step 5 and Step 6 outputs.

---

### Task 2: `run_steps` — streaming events, stop handle, richer results

**Files:**
- Modify: `get_haiggoh_tui/runner.py` (`StepResult`, `run_steps`, `_run_release_installer`; add `RunControl`, `ExecResult`)
- Test: `tests/tui/test_runner.py` (append a new `class LiveRunTests`)

**Interfaces:**
- Produces:
  - `@dataclass class ExecResult: returncode: int | None; output: str; timed_out: bool = False; cancelled: bool = False`
  - `StepResult(step, ok, output, outcome: str = "", after_version: str | None = None)`, with `__post_init__` setting `outcome = "ok" if ok else "failed"` when it is empty. Valid outcomes: `ok | failed | timed_out | cancelled | skipped`. Existing positional constructors keep working.
  - `class RunControl` (thread-safe, `threading.Lock`): `stop: str | None` (read-only property); `request_stop(mode: Literal["after_current", "immediate"]) -> None` (may upgrade after_current→immediate, never downgrades; `immediate` also calls `kill_current()`); `attach(proc) -> None`; `detach() -> None`; `kill_current() -> None` (SIGTERM to `os.getpgid(proc.pid)`, swallow `ProcessLookupError`).
  - `run_steps(steps, execute=None, reread=build_rows, on_event=lambda e: None, control=None, timeout=None, stream=None) -> list[StepResult]`
  - Events: `("start", step)`, `("output", step, line: str)`, `("result", StepResult)`.
  - Stream seam: `stream(argv, *, on_line: Callable[[str], None], control: RunControl | None, timeout: float | None) -> ExecResult`; the default is `stream_execute` (Task 3).
- Semantics:
  - `execute` given ⇒ today's non-streaming path, byte-for-byte (existing tests and `self_update_then_relaunch` use it).
  - `execute is None` ⇒ every argv (plugin, brew, git, the release-installer's `/bin/bash asset`) goes through `stream`, with `on_line=lambda l: on_event(("output", step, l))`.
  - Stop is checked BEFORE each step. `immediate` ⇒ the step becomes `skipped`. `after_current` ⇒ skipped only when `step.name` differs from the previous started step's name, so a two-step item finishes.
  - A skipped step emits `("result", r)` with `ok=False`, `outcome="skipped"`, `output=""`, and no reread.
  - An `ExecResult.timed_out` ⇒ `outcome="timed_out"`, ok False. `cancelled` ⇒ `outcome="cancelled"`, ok False. Both still re-read state for the rows.
  - `after_version = after_rows[name].installed` when the row exists.

- [ ] **Step 1: Write failing tests** (reuse `step`, `row`, `Reread` from the file; add `FakeStream(lines_by_name, results_by_name)` recording calls and emitting lines through `on_line`):
  - `test_events_in_order_with_output`: two steps, stream emits `["a","b"]` for the first ⇒ event kinds `start, output, output, result, start, result`; output events carry the step and the line.
  - `test_execute_given_keeps_legacy_path`: `execute=FakeExec()` ⇒ `FakeExec.calls` equals the argvs and `FakeStream` is never called.
  - `test_stop_after_current_finishes_item_then_skips`: steps `[free-agents/plugin, free-agents/brew, waypoints/plugin]`; `on_event` calls `control.request_stop("after_current")` on the first `start` ⇒ outcomes `["ok"|"failed", <ran>, "skipped"]` and the stream was called exactly twice.
  - `test_stop_immediate_skips_rest`: request `immediate` on the first `start`; the stream returns `ExecResult(None, "", cancelled=True)` ⇒ outcomes `["cancelled", "skipped", "skipped"]`.
  - `test_timed_out_outcome`: the stream returns `timed_out=True` ⇒ `outcome == "timed_out"`, `ok is False`, and the next step still runs.
  - `test_after_version_from_reread`: an update whose reread moves to `0.15.0` ⇒ `after_version == "0.15.0"`.
  - `test_step_result_positional_compat`: `StepResult(s, True, "ok").outcome == "ok"`; `StepResult(s, False, "x").outcome == "failed"`.
- [ ] **Step 2:** Run `python3 -m pytest tests/tui/test_runner.py -q`; the new tests FAIL and the old tests PASS.
- [ ] **Step 3:** Implement as specified above. `stream` defaults lazily to `stream_execute`; until Task 3, define `stream_execute` as a stub that raises `NotImplementedError`, so the default path is visibly unbuilt.
- [ ] **Step 4:** Run the whole `test_runner.py`; everything PASSES (the 12 old tests are unchanged).
- [ ] **Step 5: Discriminant.** Temporarily make the `after_current` check ignore the name comparison; `test_stop_after_current_finishes_item_then_skips` must go RED. Revert, then confirm with `git diff` that only the intended hunks remain.
- [ ] **Step 6: Commit** `get_haiggoh_tui/runner.py tests/tui/test_runner.py` — `feat(runner): streaming events, RunControl stop handle, step outcomes`.

🧪 **Receipt 2:** the pass line and the RED line from the mutation.

---

### Task 3: `stream_execute` — line streaming, timeout, process-group kill

**Files:**
- Modify: `get_haiggoh_tui/runner.py` (replace the stub)
- Create: `tests/tui/test_stream_exec.py`

**Interfaces:**
- Produces: `stream_execute(argv, *, on_line, control=None, timeout=None, kill_grace: float = 2.0) -> ExecResult`.
- Approach:
  - `subprocess.Popen(argv, stdout=PIPE, stderr=STDOUT, stdin=DEVNULL, start_new_session=True)` in binary mode.
  - A reader thread splits on `\n` AND `\r`, decodes each chunk with `errors="replace"`, accumulates the full output, and calls `on_line` for each non-empty piece. A final piece without a newline is still delivered.
  - The main loop `proc.wait(0.05)` polls against a monotonic deadline. On timeout: `os.killpg(pgid, SIGTERM)`, wait `kill_grace`, then `SIGKILL`, and return `timed_out=True`.
  - `control.attach(proc)` while running and `detach()` in a `finally`. `cancelled=True` when `control.stop == "immediate"` and the process died by a signal.
  - `FileNotFoundError` / `PermissionError` from Popen ⇒ `ExecResult(None, f"{argv[0]}: command not found" | str(exc))`, never raised.
  - Join the reader thread (timeout 1 s) before returning.

- [ ] **Step 1: Write failing tests.** All children are `[sys.executable, "-c", CODE]`; no case may wait longer than 3 s.
  - `test_lines_stream_before_exit`: the child prints `one`, flushes, sleeps 0.3, prints `two`. The first `on_line` arrives at least 0.2 s before the function returns (record `time.monotonic()`). `output` contains both lines and `returncode == 0`.
  - `test_timeout_kills_process_group`: the child spawns a grandchild `sleep(30)` (via `subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])`), prints the grandchild pid, then sleeps 30. Use `timeout=0.5, kill_grace=0.2` ⇒ `timed_out`, return within 2 s, and `os.kill(gpid, 0)` raises `ProcessLookupError` (after a ≤1 s retry loop).
  - `test_immediate_cancel_kills`: a thread calls `control.request_stop("immediate")` 0.3 s after start ⇒ `cancelled is True`, return within 1.5 s.
  - `test_non_utf8_and_no_newline`: the child writes `b"caf\xe9\rdone"` without a newline ⇒ `on_line` received `"caf�"` and `"done"`, no exception.
  - `test_missing_command_is_a_result_not_an_exception`: `argv=["/nonexistent/brew", "x"]` ⇒ `returncode is None` and `"not found" in output`.
- [ ] **Step 2:** Run `python3 -m pytest tests/tui/test_stream_exec.py -q`; expected FAIL (`NotImplementedError`).
- [ ] **Step 3:** Implement as specified above.
- [ ] **Step 4:** Run `python3 -m pytest tests/tui/test_stream_exec.py tests/tui/test_runner.py -q -p no:cacheprovider`; PASS. Time the file: `--durations=5`, every case < 3 s.
- [ ] **Step 5: Discriminant.** Replace `os.killpg(pgid, …)` with `proc.terminate()`; `test_timeout_kills_process_group` must go RED (the grandchild survives). Revert. Separately, make the reader use `readline()` only (no `\r` split); `test_non_utf8_and_no_newline` must go RED. Revert, then confirm with `git diff` that the tree is clean apart from the real change.
- [ ] **Step 6: Commit** `get_haiggoh_tui/runner.py tests/tui/test_stream_exec.py` — `feat(runner): streaming executor with timeout and process-group kill`.
- [ ] **Step 7: QC-1** (see the milestones table above).

🧪 **Receipt 3:** the pass line, the durations, both RED lines, the QC-1 verdict table, and the model/route used.

---

### Task 4: Step timeout from the environment

**Files:**
- Modify: `get_haiggoh_tui/runner.py`
- Test: `tests/tui/test_runner.py` (`class TimeoutEnvTests`)

**Interfaces:**
- Produces: `step_timeout_from_env(env: Mapping[str, str] = os.environ) -> float | None`; raises `ValueError` with a message containing `GET_HAIGGOH_STEP_TIMEOUT` and the raw value. Constant `DEFAULT_STEP_TIMEOUT = 600.0`.

- [ ] **Step 1: Write the failing tests** (`unset → 600.0`, `"90" → 90.0`, `"2.5" → 2.5`, `"0" → None`, `"-1" → None`, `"abc"` raises with `"GET_HAIGGOH_STEP_TIMEOUT"` and `"abc"` in `str(exc)`, `""` → 600.0, `"nan"` and `"inf"` both raise).
- [ ] **Step 2:** Run them; expected FAIL.
- [ ] **Step 3:** Implement. `float()` the value, then reject a non-finite result (`math.isfinite`).
- [ ] **Step 4:** Run them; expected PASS.
- [ ] **Step 5: Commit** `get_haiggoh_tui/runner.py tests/tui/test_runner.py` — `feat(runner): GET_HAIGGOH_STEP_TIMEOUT parsing (invalid fails loudly)`.

🧪 **Receipt 4:** the pass line. Discriminant: make `"abc"` return 600; the test goes RED. Revert.

---

### Task 5: `runstate.py` — the run model and every painted string (pure)

**Files:**
- Create: `get_haiggoh_tui/runstate.py`
- Create: `tests/tui/test_runstate.py`

**Interfaces:**
- Consumes: `Step` (routes), `StepResult` (runner, Task 2).
- Produces:
  - `SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"`, `ASCII_SPINNER = "|/-\\"`, `spinner_frames(env=os.environ) -> str`.
  - `bar(done: int, total: int, width: int = 10) -> str`: `"▐" + "█"*k + "░"*(width-k)` with `k = round(width*done/total)`, and `total == 0` ⇒ all `░`.
  - `fmt_elapsed(seconds: float) -> str` (`m:ss`, `h:mm:ss` from 1 h).
  - `cell_width(s: str) -> int` (stdlib `unicodedata`: W/F ⇒ 2; Mn/Me/Cf ⇒ 0; else 1). `clamp(s: str, width: int) -> str` (≤ width cells, trailing `…` when cut).
  - `PULSE = "▁▂▃▄▅▆▇█▇▆▅▄▃▂"`.
  - `@dataclass class RunState`, with fields:
    - `op: str`, `steps: list[Step]`, `started: float`
    - `items: list[str]` (derived: unique names in step order)
    - `current: Step | None = None`, `step_started: float | None = None`
    - `results: list[StepResult]`, `stop: str | None = None`, `finished: bool = False`
    - a private lock and `_last_line: str`
  - `RunState` methods:
    - `on_start(step, now)` and `on_result(result)`.
    - `note_output(line: str)`: thread-safe. It strips ANSI CSI/OSC escapes, keeps the text after the last `\r`, strips whitespace, and ignores empty lines. Starting a new step clears it.
    - `last_line -> str` (property).
    - `item_steps(name) -> tuple[int, int]` (done, total).
    - `item_position() -> tuple[int, int]` (1-based index of the current item, number of items).
    - `outcome_of(name) -> str | None`: None until all of the item's steps have results; then `ok` if all are ok, else the first non-ok outcome.
    - `row_decoration(row, frame: int, now: float, frames: str) -> str | None`: None when `row.name` is not in the run.
    - `dim_line(frame, now, width, frames) -> str`.
    - `subtitle(now) -> str`.
- Exact strings (tests pin them):
  - Running row: `f"{frames[frame % len(frames)]} {bar(done, total)} {installed or '—'} → {target}"`, where `target` is `row.latest or '?'` for update/install and `removing` for uninstall (then `f"{spin} {bar} removing"`).
  - Finished rows:
    - ok update/install ⇒ `f"✓ {after_version or row.installed or ''}".rstrip()`
    - ok uninstall ⇒ `"✓ removed"`
    - failed ⇒ `"✗ failed"`, timed_out ⇒ `"✗ timed out"`, cancelled ⇒ `"✗ cancelled"`, skipped ⇒ `"– skipped"`
  - Queued (in the run, not started): `"· queued"`.
  - Dim line: `clamp(f"▸ {text} · step {k}/{n} · item {i}/{N} · {fmt_elapsed(now - step_started)} {PULSE[frame % len(PULSE)]}", width)`, where `text` = `last_line` if non-empty else `shlex.join(current.argv)` (or `current.note`), and `k/n` = this item's step index/total. Before the first start: `"▸ starting…"`.
  - Subtitle: `f"{EMOJI[op]} {op.capitalize()} — item {i} of {N} · {fmt_elapsed(now - started)}"`, with `EMOJI = {"update": "⬆️", "install": "📥", "uninstall": "🗑️"}`.

- [ ] **Step 1: Write failing tests** (no Textual import in this file; it must run under the pipx pytest):
  - `test_spinner_frames_locale` (`{}` ⇒ braille; `{"LC_ALL": "C"}` ⇒ ASCII; `{"LANG": "POSIX"}` ⇒ ASCII; `{"LC_ALL": "C.UTF-8"}` ⇒ braille; `{"LC_ALL": "", "LANG": "C"}` ⇒ ASCII).
  - `test_bar` (`bar(0,2)=="▐░░░░░░░░░░"`, `bar(1,2)=="▐█████░░░░░"`, `bar(2,2)=="▐██████████"`, `bar(0,0)=="▐░░░░░░░░░░"`).
  - `test_fmt_elapsed` (`14 → "0:14"`, `75.9 → "1:15"`, `3725 → "1:02:05"`).
  - `test_running_row_decoration` (outdated row 0.8.0 → 0.9.1, one step, frame 0 ⇒ `"⠋ ▐░░░░░░░░░░ 0.8.0 → 0.9.1"`).
  - `test_two_step_item_bar_advances` (free-agents plugin+brew: after the first result and the second start ⇒ the bar part is `▐█████░░░░░`).
  - `test_finished_decorations` (one case per outcome, exact strings above).
  - `test_queued_and_not_in_run` (`"· queued"`; `None` for a row outside the run).
  - `test_dim_line_heartbeat_when_silent` (no output ⇒ contains `shlex.join(argv)`, `step 1/1`, `item 1/2`, `0:14`; frames 0 and 1 give different strings).
  - `test_dim_line_shows_last_output` (`note_output("Cloning…")` ⇒ starts with `"▸ Cloning…"`).
  - `test_note_output_strips_ansi_and_carriage_returns` (`"\x1b[32m 45%\r 90%\x1b[0m"` ⇒ `last_line == "90%"`).
  - `test_dim_line_clamps_to_width` (40-char item name, width 30 ⇒ `cell_width(s) <= 30` and `s.endswith("…")`).
  - `test_subtitle` (`"⬆️ Update — item 2 of 5 · 0:41"`).
  - `test_note_output_thread_safe` (two threads × 10 000 calls; no exception, and `last_line` is one of the written values).
- [ ] **Step 2:** Run `python3 -m pytest tests/tui/test_runstate.py -q`; expected FAIL.
- [ ] **Step 3:** Implement `runstate.py` as specified above.
- [ ] **Step 4:** Run it; expected PASS.
- [ ] **Step 5: Commit** `get_haiggoh_tui/runstate.py tests/tui/test_runstate.py` — `feat(tui): pure RunState model and run-progress strings`.

🧪 **Receipt 5:** the pass line. Discriminant: make `clamp` return `s` unchanged ⇒ `test_dim_line_clamps_to_width` RED; make the pulse ignore `frame` ⇒ `test_dim_line_heartbeat_when_silent` RED. Revert both.

---

### Task 6: Inline live run on the main list (worker, painting, locks, report)

**Files:**
- Modify: `get_haiggoh_tui/app.py`: `__init__` (`self.run_state = None`, `self._run_control = None`), `_exec_steps`, new `_start_run`, `_run_worker`, `_on_run_event`, `_finish_run`, `run_active`.
- Modify: `get_haiggoh_tui/screens.py`: `row_label` (new `deco` param), `MainScreen.rebuild_rows`, `on_mount` (timer), new `_tick_run`, the guards in the tick/mode/quit actions, new `RunReportScreen`; DELETE `ProgressScreen`.
- Modify: `get_haiggoh_tui/theme.tcss`: `#report-text` / `RunReportScreen` layout. The dim option uses the existing disabled-option style (`ansi_bright_black`), the same grey as `#summary`.
- Create: `tests/tui/test_live_run.py`.

**Interfaces:**
- Consumes: `run_steps(..., on_event, control, timeout)` (Task 2), `RunControl` (Task 2), `step_timeout_from_env` (Task 4), `RunState` and its helpers (Task 5).
- Produces:
  - `GetHaiggohApp.run_state: RunState | None` (None when idle) and `GetHaiggohApp.run_active -> bool`.
  - `_start_run(op, steps)`: parse the timeout. On `ValueError`: `notify(str(exc), severity="error")` and return, without starting.
  - `_run_worker(op, steps, control, timeout)`: decorated `@work(thread=True, exit_on_error=False, group="run", exclusive=True)`.
  - `row_label(r, ticked, mode=None, eligible=True, deco: str | None = None) -> Text`: with a `deco`, the body is `f"{r.mark} {r.name:<26} {deco}"`.
  - `class RunReportScreen(ModalScreen)`: `__init__(op, results, error: str | None = None)`; title `f"{EMOJI[op]} {op.capitalize()} report — {k} ok · {m} failed"` (failed = every non-ok, skipped included); one line per result: `✓ name (route)`, or `✗ name — route: <first non-empty output line[:100]>` / `✗ name — timed out` / `✗ name — cancelled` / `– name — skipped`; a `Done` button; `enter` / `escape` dismiss.
  - Option ids: `gap:runstatus` (disabled, empty) and `runstatus` (disabled, `Text(dim_line)`), appended after `action:quit` ONLY while `run_active`.
- Bridging rules:
  - The worker passes `on_event`, which handles `("output", …)` by calling `state.note_output(line)` directly: no `call_from_thread` per line (R2).
  - `start` and `result` go through `self.call_from_thread(self._on_run_event, e)`, which updates `RunState` and repaints that one row.
  - The worker's `finally` uses `call_from_thread(self._finish_run, results, error)`, where `error` is `f"run crashed: {exc}"` if the runner raised.
  - `_finish_run` sets `state.finished`, sets `run_state = None`, calls `refresh_after_run()`, `rebuild_rows()` and `refresh_buttons()`, and pushes `RunReportScreen`.
- Painting:
  - `MainScreen.on_mount` starts `self.set_interval(0.15, self._tick_run)`.
  - `_tick_run` returns at once when not `run_active`. Otherwise it increments `self._frame` and, for the current item's row index and the `runstatus` index only, calls `ol.replace_option_prompt_at_index(i, row_label(...)/Text(...))`. Width = `ol.scrollable_content_region.width`. It also updates `#subtitle` with `state.subtitle(now)`.
  - `rebuild_rows` derives every decoration from `app.run_state` (R3), so a rebuild mid-run re-creates them.
- Locks while `run_active` (B5):
  - `q` and `action:quit` ⇒ `notify("Run in progress — esc to cancel")`, no exit.
  - `space`, `a`, `n`, `u`, `i`, `x`, `enter`-to-run and the run buttons do nothing.
  - Arrows, hover and the info box keep working.
  - `escape` is wired in Task 7. In this task it does nothing while running.

- [ ] **Step 1: Write the failing pilot tests** in `test_live_run.py`:
  - Setup: `pytest.importorskip("textual")`, and `make_rows` / `row` copied from `test_app_pilot.py`'s helpers. Import them with `from tests.tui.test_app_pilot import make_rows, make_app` if the package import works; otherwise copy them and say so in the receipt.
  - Add a `GatedRunner(lines=("resolving…",), outcome="ok", raise_exc=None)` with these properties:
    - Its `__call__(steps, on_event=..., control=None, timeout=None, **kw)` emits `start` and then each line as `output` for every step.
    - It sets `self.started` (`threading.Event`), then waits on `self.release` (`threading.Event`) in 0.02 s slices, ending early on `control.stop == "immediate"`.
    - It then emits a `result` with `after_version="9.9"`.
    - It deliberately has NO stop-skipping logic of its own. Runner semantics are Task 2's tests, and a fake that copied them would test itself.
  - Every test wraps its pilot body in `asyncio.wait_for(…, 10)`. A run that blocks the UI then fails with a timeout instead of hanging.
  - The tests:
    - `test_run_does_not_block_ui`: enter update mode, run, wait for `runner.started`. Then `pilot.press("down")` changes `ol.highlighted`, `app.screen` is a `MainScreen` (no modal), and `app.run_active` is True. Release; after ≤2 s `app.run_active` is False and the screen is a `RunReportScreen`.
    - `test_running_row_has_spinner_and_bar`: while gated, the waypoints row prompt's plain text contains a char of `SPINNER` and `"▐"`, placed after `"waypoints"`.
    - `test_dim_line_below_quit_after_gap`: while gated, the option ids end with `["action:quit", "gap:runstatus", "runstatus"]`; the `runstatus` prompt starts with `"▸ resolving…"`; the option is disabled (dim style). After the run, neither id is present.
    - `test_heartbeat_changes_without_output`: use `GatedRunner(lines=())`. Sample the `runstatus` prompt, `await pilot.pause(0.4)`, sample again: the two strings differ. (If pilot sampling turns out blind, record frames inside `_tick_run` through a test-only list and assert on that. Say which one you used.)
    - `test_row_flips_when_step_finishes`: release ⇒ the waypoints prompt contains `"✓ 9.9"` before the report is dismissed.
    - `test_report_lists_results`: a runner whose two items give ok and failed (output `"brew: command not found\nmore"`) ⇒ the report's text has `"1 ok · 1 failed"`, `"✓ waypoints (plugin)"` and `"brew: command not found"`, and not `"more"`.
    - `test_q_does_not_quit_during_run`: while gated, press `q` ⇒ the app is still running, and a notification containing `"esc to cancel"` exists.
    - `test_ticks_and_modes_inert_during_run`: while gated, press `space`, `a`, `u`, `i`, `x` ⇒ `app.mode is None`, `app.ticks` is unchanged, and `runner.calls` has length 1.
    - `test_refresh_mid_run_keeps_decorations`: while gated, call `app._apply_rows(make_rows())` ⇒ the waypoints prompt still has the spinner.
    - `test_runner_crash_unlocks_and_reports`: `GatedRunner(raise_exc=RuntimeError("boom"))` ⇒ the report contains `"run crashed: boom"`, and `app.run_active` is False.
    - `test_flood_of_output_keeps_ui_responsive`: `GatedRunner(lines=[f"l{i}" for i in range(5000)])` ⇒ while gated, `press("down")` moves the highlight within the 10 s wait_for, and the dim line shows `l4999`.
    - `test_dim_line_single_line_in_narrow_terminal`: `run_test(size=(50, 40))` ⇒ the `runstatus` prompt's `cell_width` ≤ the list's content width.
    - `test_invalid_timeout_refuses_to_run`: env `GET_HAIGGOH_STEP_TIMEOUT=abc` (patched with `mock.patch.dict(os.environ)`) ⇒ `runner.calls == []` and an error notification names the variable.
  - Update the existing tests that asserted on `ProgressScreen` (find them with `grep -n "ProgressScreen\|progress-out" tests/`) to assert on `RunReportScreen` instead. List each change in the receipt.
- [ ] **Step 2:** Run `~/.local/share/get-haiggoh/tui-venv/bin/python -m pytest tests/tui/test_live_run.py -q -rs`; expected FAIL, with 0 skipped.
- [ ] **Step 3:** Implement `app.py` per the Interfaces block.
- [ ] **Step 4:** Implement `screens.py` and `theme.tcss` per the Interfaces block. Delete `ProgressScreen`, then `grep -rn ProgressScreen get_haiggoh_tui tests` ⇒ no hits.
- [ ] **Step 5:** Run the full TUI suite under the venv with `-rs`; everything PASSES with 0 skipped.
- [ ] **Step 6: Discriminants.** Each mutation is temporary and must go RED; revert after each, then check `git diff`:
  - (a) In `_start_run`, call `self.runner(...)` synchronously instead of starting the worker ⇒ `test_run_does_not_block_ui` RED (timeout).
  - (b) Stop appending the `runstatus` option ⇒ `test_dim_line_below_quit_after_gap` RED.
  - (c) Remove the `set_interval` ⇒ `test_heartbeat_changes_without_output` RED.
  - (d) In `rebuild_rows`, ignore `run_state` ⇒ `test_refresh_mid_run_keeps_decorations` RED.
- [ ] **Step 7: Commit** `get_haiggoh_tui/app.py get_haiggoh_tui/screens.py get_haiggoh_tui/theme.tcss tests/tui/test_live_run.py` plus any updated test files — `feat(tui): inline non-blocking bulk run with live row, dim heartbeat line and report`.
- [ ] **Step 8: QC-2.**

🧪 **Receipt 6:** the pass line (0 skipped), the four RED lines, the QC-2 table, and the model/route used.

---

### Task 7: Cancel — Esc dialogs, double-Esc, ctrl+q

**Files:**
- Modify: `get_haiggoh_tui/app.py` (`on_run_escape`, `cancel_run`, `action_quit` override).
- Modify: `get_haiggoh_tui/screens.py` (`MainScreen.action_back` while running; new `CancelConfirmScreen`, `CancelModeScreen`).
- Create: `tests/tui/test_live_run_cancel.py`.

**Interfaces:**
- Produces:
  - `GetHaiggohApp.on_run_escape(now: float | None = None) -> None`:
    - It stores `self._last_esc` (monotonic).
    - If the previous Esc was ≤ 0.5 s ago, it calls `cancel_run("immediate")` and pops any `CancelConfirmScreen`/`CancelModeScreen` on the stack.
    - Otherwise, if no cancel dialog is showing, it pushes `CancelConfirmScreen()`.
  - `cancel_run(mode)` ⇒ `self._run_control.request_stop(mode)`, sets `run_state.stop = mode`, and notifies `"Stopping after the current item…"` or `"Cancelling…"`.
  - `CancelConfirmScreen(ModalScreen)`:
    - Text `"Cancel the run? y/n"`, buttons `Yes` / `No`, keys `y` / `n`.
    - `escape` calls `app.on_run_escape()`; that covers the double-Esc. A single later Esc dismisses the dialog.
    - Yes ⇒ dismiss and push `CancelModeScreen`. No ⇒ dismiss, and the run continues.
  - `CancelModeScreen(ModalScreen)`:
    - Option `f`, button text `"Finish current item, then stop"` ⇒ `cancel_run("after_current")`.
    - Option `c`, button text `"Cancel and stop immediately"` ⇒ `cancel_run("immediate")`.
    - Fixed warning line (B7): `"Stopping immediately kills the running command — it can leave a plugin half-updated or a Homebrew lock behind."`
    - `escape` ⇒ dismiss, with no cancel.
  - `GetHaiggohApp.action_quit()` (ctrl+q): while `run_active` ⇒ the same notice as `q`, no exit. Otherwise `super().action_quit()` (`self.exit()`).
  - `_finish_run` dismisses any cancel dialog still open before it pushes the report.

- [ ] **Step 1: Write the failing pilot tests.** Use the `GatedRunner` from `test_live_run.py` (import it, or move it into a shared `tests/tui/live_rig.py` — a name the test glob does not match — and import it in both files). Every body is wrapped in `wait_for(…, 10)`.
  - `test_single_esc_opens_confirm`: while gated, `escape` ⇒ `CancelConfirmScreen`; `n` ⇒ back on `MainScreen`, the run is still active, and `control.stop is None`.
  - `test_yes_then_finish_current`: `escape`, `y`, `f` ⇒ `control.stop == "after_current"` and the run is still active; release ⇒ the report shows the second item as `skipped`.
  - `test_yes_then_immediate`: `escape`, `y`, `c` ⇒ `control.stop == "immediate"`; the report has `cancelled`; the `CancelModeScreen` text contains `"half-updated"`.
  - `test_double_escape_is_immediate`: `pilot.press("escape", "escape")` (a single call, so it lands within 0.5 s) ⇒ `control.stop == "immediate"`, no cancel dialog on the stack, and the report appears.
  - `test_slow_second_escape_just_dismisses`: `escape`, `pause(0.7)`, `escape` ⇒ the dialog is gone, `control.stop is None`, and the run is active.
  - `test_ctrl_q_blocked_during_run`: `ctrl+q` while gated ⇒ the app is still running.
  - `test_esc_outside_run_still_leaves_mode`: in update mode, not running, `escape` ⇒ `app.mode is None` (the existing behaviour is unchanged).
- [ ] **Step 2:** Run the file; expected FAIL with 0 skipped.
- [ ] **Step 3:** Implement per the Interfaces block.
- [ ] **Step 4:** Run the full TUI suite under the venv with `-rs`; everything PASSES with 0 skipped.
- [ ] **Step 5: Discriminant.** Widen the double-Esc window to 0 s ⇒ `test_double_escape_is_immediate` RED. Make `CancelModeScreen`'s `f` request `immediate` ⇒ `test_yes_then_finish_current` RED. Revert both.
- [ ] **Step 6: Commit** — `feat(tui): Esc cancel dialogs, double-Esc immediate stop, ctrl+q guard`.
- [ ] **Step 7: QC-3.**

🧪 **Receipt 7:** the pass line, the RED lines, and the QC-3 table.

---

### Task 8: Version 0.11.0, docs, portable regen, screenshots, full gate, push

**Files:**
- Modify: `.claude-plugin/plugin.json` (`"version": "0.11.0"`) and `CHANGELOG.md` (new top entry `## [0.11.0] — <date>`).
- Modify: the README's TUI section, if Phase 0's grep found one describing the run screen.
- Regenerate: `portable/`, via `python3 scripts/build-portable.py` (read its `--help` first; never hand-edit `portable/`).

- [ ] **Step 1:** Bump `plugin.json`. Write the CHANGELOG entry in user-facing words: the TUI no longer freezes during bulk runs; the running row shows a spinner and per-item bar; a dim status line sits under Quit; Esc cancels (finish current / immediate, double-Esc); `GET_HAIGGOH_STEP_TIMEOUT` (default 600 s; an invalid value refuses to run); a closing report; and the ship gate now runs the TUI pilot tests.
- [ ] **Step 2:** Regenerate `portable/`, then `python3 scripts/build-portable.py --check; echo EXIT:$?` ⇒ `EXIT:0`. `grep -rn '"version"' .claude-plugin/plugin.json portable/.claude-plugin/plugin.json` ⇒ both `0.11.0`.
- [ ] **Step 3: Screenshots** (playbook rule 5). Write a throwaway script OUTSIDE the repo (`$TMPDIR/gh-shots.py`) that drives `make_app` + `GatedRunner` with `run_test(size=(100, 40))` and calls `app.save_screenshot(<path>)` in four states: running with two items, `CancelConfirmScreen`, `CancelModeScreen`, `RunReportScreen`. Convert each with `rsvg-convert -o x.png x.svg`, Read each PNG, and compare it against the spec mockups: the spinner and bar right after the name, ONE blank row between `Q) Quit` and the dim line, the dim line grey and single-line. Note any mismatch, fix it, and re-shoot.
- [ ] **Step 4: Full gate.** Run the exact `test_cmd` from `rtc-ship.json`: `sh -c '<test_cmd>' > /tmp/gh-gate-final.log 2>&1; echo EXIT:$?` ⇒ `EXIT:0`, and the TUI half reports 0 skipped. Quote both summary lines.
- [ ] **Step 5: Commit** `.claude-plugin/plugin.json CHANGELOG.md portable README.md` (README only if changed) — `chore(0.11.0): version, changelog, portable regen`.
- [ ] **Step 6: QC-4** (gate log + screenshots + version grep).
- [ ] **Step 7: Push the branch** (allowed now): `git push -u origin feat/tui-live-run-progress`, then confirm with `git ls-remote origin feat/tui-live-run-progress` that the sha matches `git rev-parse HEAD`.

🧪 **Receipt 8:** the `--check` exit, the version grep, the four screenshot paths with one line each on what was checked, the gate summary lines, and the ls-remote sha.

---

### Task 9: Ship and dogfood — STOP for the user's go

- [ ] **Step 1: Stop and ask.** Ask the user (AskUserQuestion) for the ship depth: (a) stop at the pushed branch; (b) merge + tag + release via `rtc-ship`; (c) (b) plus refresh the installed plugin and a live dogfood with them watching. Do nothing past Task 8 without an answer.
- [ ] **Step 2 (if b/c):** Ship from the WORKTREE with the installed rtc-ship (`run-to-completion:ship` skill). Do NOT set `RTC_SKIP_TESTS`. Verify with `git ls-remote origin refs/tags/v0.11.0` and `gh release view v0.11.0`.
- [ ] **Step 3 (if c):** `get-haiggoh` plan/apply. Confirm `claude plugin list` shows get-haiggoh 0.11.0, and that the installed copy contains `get_haiggoh_tui/runstate.py` (that checks the content, not just the version string).
- [ ] **Step 4 (if c): Live dogfood — needs the user's eyes.** They open the TUI in a real terminal (`get-haiggoh-tui`), enter update mode with at least one outdated item, and press update. The receipt records what they report: spinner and bar visible within 1 s, list scrollable during the run, dim line under Quit, report at the end. If nothing is outdated, say so; never claim the live check.

🧪 **Receipt 9:** the ls-remote tag sha, the release URL, the `plugin list` line, the content check, and the user's dogfood observations (or "not run — reason").

**Closing step:** run `lasting-plans complete "docs/superpowers/plans/2026-11-24-tui-live-run-progress.md"`. Per plan-airtight end-of-life for repo plans: the Status flip goes on a short-lived `docs/plan-tui-live-run-complete` branch, pushed for the user to fast-forward. The executor never merges it.

---

## 🧨 Adversarial review

- **Pilots run under the pipx pytest.** Shortcut → "all green" with every pilot skipped → a frozen UI ships. Rule: Task 1's `GET_HAIGGOH_REQUIRE_TEXTUAL` gate. Detect: Receipt 1's planted skip goes RED.
- **A test asserts after the run instead of during it.** A synchronous run still ends with the right report → green while blocking. Rule: assertions happen while `GatedRunner` holds, inside `wait_for`. Detect: mutation 6(a) RED.
- **A fake copies the runner's stop logic.** The UI tests pass against the fake's own semantics → cancel-mode bugs hide. Rule: `GatedRunner` has no stop-skipping; stop semantics live in Task 2's tests against the real `run_steps`. Detect: QC-2/QC-3 brief item "fakes that copy the implementation".
- **`proc.terminate()` instead of `killpg`.** Child dies, `brew`'s grandchild keeps the lock → "cancelled" but still running. Detect: mutation 3 (grandchild survives ⇒ RED).
- **`call_from_thread` per output line.** Works in tests with 3 lines; a chatty brew blocks the worker on the UI → slow runs, laggy UI. Rule: output goes through `note_output` only. Detect: `test_flood_of_output_keeps_ui_responsive`.
- **Invalid timeout silently becomes 600.** Looks friendly; the user's explicit setting is ignored without notice. Rule: Deviation B6. Detect: Task 4 discriminant, `test_invalid_timeout_refuses_to_run`.
- **Hand-editing `portable/plugin.json`.** Version looks bumped; the freshness test or `--check` fails at ship, or the generated file drifts. Rule: regenerate. Detect: Task 8 Step 2 `--check`.
- **Editing the plugin cache to "test the installed copy".** Passes locally, reverted by the next update, never shipped. Rule: system instruction 2.
- **Reading a branch push as permission to merge.** Rule: authority matrix; Task 9 Step 1 asks first.
- **Pipeline hides the exit code** (`pytest … | tail`). Rule: redirect to a file and `echo EXIT:$?` (every gate step is written that way).
- **Switching the canonical checkout to the feature branch to dogfood.** Changes what the user's launcher runs. Rule: system instruction 2; dogfood only after ship (Task 9).

**Cannot be tested safely here:** a real `brew` lock left by an immediate cancel (R1); a real execv self-update mid-run (B8; unchanged code path). Both are named in the report and not claimed.

## 🏁 Final review and delivery (executor fills in)

- Implemented versus planned, task by task. Receipts that ran, with their pass lines. Tests that did not run, and why.
- Pilot skips in the final gate: must be 0, quoted.
- User work preserved: `git status` in the worktree and the canonical checkout, both clean or explained.
- The highest boundary actually crossed: push / merge / tag / release / refresh, matched against the user's Task 9 answer.
- The delivered plan file and CHANGELOG re-read after the last commit.
- Then the closing step above.
