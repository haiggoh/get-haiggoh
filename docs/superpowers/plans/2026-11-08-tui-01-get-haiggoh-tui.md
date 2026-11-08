# get-haiggoh TUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (native: the executor does every task itself, then one final review). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `get-haiggoh` with no arguments opens a CSL-style Textual TUI that lists every haiggoh plugin and related tool with installed/latest status, installs/updates/uninstalls ticked rows in bulk, explains each item in an info box, and opens each item's own menu.

**Architecture:** Pure-logic modules (stdlib only, plain pytest) decide everything — inventory, ticks, routes, the 🍺 Homebrew gate, menu-spec v1, the step runner. A thin Textual layer (`app.py`, `screens.py`) only renders and dispatches. A stdlib bootstrap (`bin/get-haiggoh-tui`) owns a private venv and falls back to the existing `get-haiggoh-menu`.

**Tech Stack:** Python 3 stdlib; Textual 3.7.1 + the CSL pin set in a private venv; pytest (+ Textual `run_test` pilot inside the venv).

**Spec:** `docs/superpowers/specs/2026-11-08-get-haiggoh-tui-design.md`. Index: `2026-11-08-tui-00-index.md`.

## Global Constraints

- Pins copied verbatim from `free-agents/install/session-picker-requirements.txt` (*confirmed live* 2026-11-08: `textual==3.7.1`, `rich==15.0.0`, …) into `tui-requirements.txt`, with a header naming that source.
- Brand marks come from `docs/branding.md` § Marks — never typed in code. Homebrew is always written `🍺 Homebrew` in UI copy.
- Back item copy, exact: `👨🏻‍💻 Back to Get Haiggoh`, always the LAST action, only when opened from get-haiggoh.
- 🍺 notice copy, exact (names list dynamic): `🍺 Homebrew will be installed now — it makes future updates of {names} easier. It asks for your Mac password once.` Buttons: `Install 🍺 Homebrew` / `Continue without 🍺 Homebrew`.
- State files sit next to the existing ones (*confirmed live*: `skip_list_path()` = `~/.claude/.get-haiggoh-skip.json`): `~/.claude/.get-haiggoh-tui-state.json` (env `GET_HAIGGOH_TUI_STATE_FILE`), `~/.claude/.get-haiggoh-tui-pending.json` (env `GET_HAIGGOH_TUI_PENDING_FILE`). Venv `~/.local/share/get-haiggoh/tui-venv` (env `GET_HAIGGOH_TUI_VENV`). A SET-but-invalid override aborts naming the variable.
- No module except `app.py`/`screens.py` imports Textual.
- Every new script supports `--help` and rejects unknown flags (exit 2, usage on stderr) BEFORE any side effect.
- Tests never touch real `~/.claude`, real brew, real `claude plugin`: the `World` fixture env overrides + a `FakeExec` that records argv.
- Version: get-haiggoh **0.10.0** on every surface `rtc-ship.sh --versions-only` reports.

## Review Focus

1. **A legacy menu probed with `--menu-spec` RUNS instead** (e.g. `backup.sh` reads an unknown arg as a destination and writes). Expect: never probe — call `--menu-spec` only when the installed version ≥ the item's declared `spec_min_version`. Test in Task 6.
2. **An `unverified` row** (remote check failed) must never render ✓. Expect `? unverified` + the diagnostic in the info box. Test in Task 2.
3. **Offline / GitHub unreachable at launch.** Expect instant paint from cache, refresh failure shown in the summary line, no crash. Test in Task 2.
4. **Bulk run where one step fails midway.** Expect the rest still run, failures listed at the end with their output, final state re-read from disk (not exit codes). Test in Task 5.
5. **Crash leftover pending file.** Expect a Resume/Discard prompt, never silent replay; `--resume` consumes it exactly once. Test in Task 5.

## Quality-control milestones (standing rule — user, 2026-11-08)

Procedure: `~/.claude/plans/_PLAYBOOKS/Playbook-milestone-qc-offload-test-proof.md`. **At each
milestone below, run /offload (free-agents:offload) — a stateless dispatch to an out-of-family reviewer
— with that playbook's brief, attaching the task text, tests, fixtures and implementation. Pay special
attention to the test fixtures: they must actually prove what this plan demands, not go green without
the requirement being fulfilled. Run every proposed mutation (must go RED); fix or rebut each finding
with evidence. Do not start the next task with an open finding.** The verdict table + mutation RED lines
are part of that task's receipt.

| Milestone | Requirements under review |
|---|---|
| M1 after Task 2 | no-network cached paint; skipped-missing stays `missing`; `unverified` never ✓; offline tool status |
| M2 after Task 5 | update never installs; self first + resume once; failures don't stop the rest; `ok` from re-read state |
| M3 after Task 6 | never probe below `spec_min_version`; argv never shell-joined; Back always last |
| M4 after Task 7 | tick defaults on first/later launch; 🍺 notice only when needed + decline fallback; info box follows highlight+hover; pilot run 0 skipped |
| M5 before Task 9 ship | whole-branch: every spec requirement → its proving test (UNPROVEN ⇒ hold the ship) |

## Authority matrix

| Operation | Authority |
|---|---|
| Edits + commits on branch `feat/tui` in a worktree of get-haiggoh | allowed now |
| Creating the private venv on this machine; installing PyPI pins into it | allowed now (download ≈ 10 MB) |
| Running real `claude plugin` / `brew` commands | only in the Task 9 dogfood, against items the user already has; **never** uninstall a real item, never install real 🍺 Homebrew (it is present) |
| `rtc-ship.sh` for get-haiggoh 0.10.0: gates, merge to `main`, tag, release, plugin refresh | allowed after Task 8 receipts are all green |
| Changes in any OTHER repo (free-agents, waypoints, …) | **prohibited here** — that is Plan 3 |
| Force-push, moving a published tag, editing `~/.claude/plugins/cache`, hand-editing `installed_plugins.json` | **prohibited** |

Highest granted boundary: **release of get-haiggoh 0.10.0 + installed-copy refresh + dogfood.**

## Phase 0 — preflight (read-only)

- [ ] Write three sentences connecting Task 1 to "a newcomer opens get-haiggoh, sees everything explained, and installs/updates with one key".
- [ ] `git -C ~/ClaudeWorkspace/get-haiggoh status --porcelain` empty; branch `docs/tui-design` (spec + plans) is merged or the worktree is cut from it.
- [ ] Create worktree `feat/tui` (superpowers:using-git-worktrees). Baseline: `pytest -n auto -q` (fallback `pytest -q`) → record count; this is the "no regression" bar.
- [ ] *Unknown to inspect:* `gh api repos/haiggoh/<repo> --jq .description` for human-shell, claude-code-transcript-distiller, mac-claude-migration, mac-iphone-backup-cloudsync, claude-code-desktop-sync → their About emoji. Any mark not yet in `docs/branding.md` § Marks gets added there in Task 1.
- [ ] *Unknown to inspect:* mac-iphone-backup-cloudsync's non-brew install route (README). Record; if none, its fallback is `null` (brew-only, shown as such).
- [ ] *Confirmed live:* `claude plugin uninstall <plugin>` exists (`claude plugin --help`).

## Task 1: Catalog data + inventory rows

**Files:** Create `catalog/related-tools.json`, `catalog/plugin-extras.json`, `get_haiggoh_tui/__init__.py`, `get_haiggoh_tui/inventory.py`, `tests/tui/test_inventory.py`. Modify `docs/branding.md` (missing marks only), `catalog-parity.py` (also check extras coverage).

**Interfaces — Produces:**
- `@dataclass Row: name: str; section: Literal["plugin","tool"]; mark: str; description: str; adds: str; installed: str | None; latest: str | None; status: Literal["current","outdated","missing","unverified"]; diagnostic: dict | None; menu: dict | None; tool: dict | None`
- `brand_marks(branding_md: str) -> dict[str, str]`
- `load_catalog(repo_root: Path) -> tuple[list[dict], list[dict], dict]` → (marketplace plugins, related tools, plugin extras)

Data shapes (*decision*):
- `related-tools.json`: `[{name, repo: "haiggoh/<r>", description, adds, formula: str|null, fallback: {kind: "release-installer"|"git", asset?: str, uninstall_argv?: [..]} | null, without_brew_loses: str|null, version_cmd: [..]|null, menu: {argv: [..], spec_min_version: null, return_to_min_version: null} | null}]` in spec order: transcript-distiller, human-shell (`without_brew_loses: "no Dock icon"`), mac-claude-migration (`formula: null` until Plan 2, `fallback.kind: "git"`), mac-iphone-backup-cloudsync.
- `plugin-extras.json`: `{<plugin>: {adds, formula?: str, menu?: {...same...}}}` — free-agents `formula: "haiggoh/tap/free-agents"`, `menu.argv: ["csl"]`; waypoints/cost-tracker/lasting-plans/check-code menus per the spec's verified list.

- [ ] **Step 1 (`local:` dispatch, Fable/strongest free reviewer lane):** draft `description` + `adds` for the 4 tools and `adds` for all 16 plugins. Brief: per item attach README + `hooks/hooks.json` + `skills/*/SKILL.md` frontmatter + `bin/` listing; output JSON only. Verify every `adds` claim against the attached files before committing (a hook that is not in hooks.json is a false claim).
- [ ] **Step 2: failing tests** — `test_every_plugin_has_extras` (names of marketplace.json == keys of plugin-extras.json), `test_every_item_has_a_mark` (all 20 names resolve via `brand_marks(open("docs/branding.md").read())`), `test_tool_order_matches_spec`, `test_brand_marks_parses_pairs` (`"free-agents 📡🦾 (lane…)"` → `📡🦾`; `"cost-tracker 💸 (never…)"` → `💸`).
- [ ] **Step 3:** implement; run → PASS. Known-bad: delete one key from plugin-extras.json → `test_every_plugin_has_extras` RED; restore.
- [ ] **Step 4:** extend `catalog-parity.py` to fail when extras/marks lag the marketplace; `tests/test_catalog_parity.py` gains that case. Commit.

## Task 2: Status — plugins and tools

**Files:** Modify `bin/get-haiggoh.py` (`_compute` signature only). Create `get_haiggoh_tui/status.py`, `tests/tui/test_status.py`.

**Interfaces — Produces:**
- `_compute(only=None, category=None, apply_skip=True, remote_versions=None)` — when `remote_versions` is given, no network at all (no manifest sweep, no `_latest_tag`). Defaults keep today's behaviour.
- `load_cli_module(repo_root: Path) -> ModuleType` (importlib on `bin/get-haiggoh.py`)
- `plugin_rows(cached: bool) -> list[Row]` — cached ⇒ `remote_versions=c.load_cached_versions(c.refresh_stamp_path())`
- `tool_status(tool: dict, run=subprocess.run, fetch=c.fetch_url) -> tuple[str|None, str|None, dict|None]` → (installed, latest, diagnostic). Installed: `brew list --versions <short formula name>` when brew present, else `version_cmd`; latest: `https://api.github.com/repos/<repo>/releases/latest` `tag_name` minus `v`.
- `build_rows(cached: bool) -> list[Row]` — get-haiggoh first, then plugins in marketplace order, then tools.

- [ ] **Step 1: failing tests** — `test_compute_with_remote_versions_makes_no_network` (monkeypatch `fetch_url`/`subprocess.run` to raise), `test_apply_skip_false_keeps_skipped_missing` (skipped missing item → status `missing`, not `unknown`), `test_unverified_never_current` (diagnostic present → `status == "unverified"`), `test_tool_status_offline` (fetch raises → `latest is None`, diagnostic set, no exception), `test_self_row_first`.
- [ ] **Step 2:** implement; existing suite still at baseline count (`pytest -n auto -q`). Known-bad: make `_compute` ignore `remote_versions` → the no-network test RED. Commit.

## Task 3: Ticks, routes, steps

**Files:** Create `get_haiggoh_tui/selection.py`, `get_haiggoh_tui/routes.py`, `tests/tui/test_selection.py`, `tests/tui/test_routes.py`.

**Interfaces — Produces:**
- `is_first_run(state_path: Path) -> bool`; `mark_first_run_done(state_path: Path) -> None` (atomic write, `{"schema": 1, "first_run_done": true}`)
- `default_ticks(rows, first_run: bool) -> set[str]` — first run: every `missing` + every `outdated`; later: `outdated` only.
- `@dataclass Step: name: str; op: Literal["install","update","uninstall"]; route: Literal["plugin","brew","release-installer","git"]; argv: list[str]; needs_brew: bool; note: str | None`
- `brew_path() -> str | None` (`shutil.which`, then `/opt/homebrew/bin/brew`, `/usr/local/bin/brew`)
- `plan_steps(rows, ticks, op, brew_present: bool, brew_allowed: bool) -> list[Step]` — op filters rows (`update` ⇒ only ticked `outdated`; `install` ⇒ only ticked `missing`; `uninstall` ⇒ ticked installed, **minus get-haiggoh**). get-haiggoh's step, when present, is first. free-agents yields a plugin step plus, if brew is usable, a brew step.

Route rules (spec § Install routes): plugin argv `["claude","plugin",<install|update|uninstall>,f"{name}@haiggoh"]`; brew argv `["brew",<install|upgrade|uninstall>,formula]`; brew route iff `formula` and (`brew_present` or `brew_allowed`), with `needs_brew = not brew_present`; else `fallback`; fallback `null` ⇒ Step with `argv=[]` and `note="needs 🍺 Homebrew"` (shown, not run).

- [ ] **Step 1: failing tests** — `test_first_run_ticks_missing_and_outdated`, `test_later_run_ticks_only_outdated`, `test_update_never_installs` (ticked missing row + op update → no step), `test_bulk_uninstall_excludes_self`, `test_self_step_first`, `test_brew_present_prefers_formula`, `test_brew_declined_uses_fallback_with_loss_note` (human-shell note contains `no Dock icon`), `test_free_agents_gets_two_steps`, `test_no_fallback_tool_is_noted_not_run`.
- [ ] **Step 2:** implement; PASS; commit.

## Task 4: 🍺 Homebrew gate

**Files:** Create `get_haiggoh_tui/brew_gate.py`, `tests/tui/test_brew_gate.py`.

**Interfaces — Produces:**
- `needs_brew(steps) -> list[str]` (names whose step has `needs_brew`)
- `notice_text(names: list[str]) -> str` (exact copy from Global Constraints; names joined `", "` with `" and "` before the last)
- `decline_lines(rows, names) -> list[str]` — `"{mark} {name}: continuing via {route}" + (" — " + without_brew_loses if set)`
- `INSTALL_ARGV = ["/bin/bash", "-c", "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"]` (*dated observation*: the official one-liner; run under `bash -c` so the `$(…)` expands) and `verify_installed() -> bool` = `brew_path() is not None` re-checked AFTER the run.

- [ ] **Step 1: failing tests** — `test_notice_exact_copy` (three names → `free-agents, human-shell and claude-code-transcript-distiller`), `test_no_notice_when_brew_present` (`needs_brew` empty), `test_decline_names_the_loss`, `test_verify_rechecks_after_run` (fake `brew_path` flips only after the fake run).
- [ ] **Step 2:** implement; PASS; commit.

## Task 5: Runner — execution, verification, self-update resume

**Files:** Create `get_haiggoh_tui/runner.py`, `tests/tui/test_runner.py`.

**Interfaces — Produces:**
- `@dataclass StepResult: step: Step; ok: bool; output: str`
- `run_steps(steps, execute=subprocess.run, reread=build_rows, on_event=lambda e: None) -> list[StepResult]` — runs all steps even after a failure; `ok` is decided by re-reading state (installed version changed as expected / row gone after uninstall), never by exit code alone. Release-installer steps download the asset into a fresh `tempfile.mkdtemp()` and run it by path.
- `write_pending(path, op, names) / read_pending(path) -> dict | None / clear_pending(path)` — `{"schema": 1, "op", "names", "created"}`; atomic.
- `self_update_then_relaunch(steps, pending_path, execv=os.execv) -> None` — if the first step is get-haiggoh and more follow: run it, `write_pending` for the rest, `execv` `bin/get-haiggoh-tui --resume`.
- On install: remove name from the skip list; on uninstall: add it (`c.load_skip_list`/`c.save_skip_list`), so the SessionStart nudge respects the choice.

- [ ] **Step 1: failing tests** — `test_failure_midway_runs_the_rest`, `test_ok_from_reread_not_exit_code` (exit 0 but version unchanged → `ok False`), `test_self_update_writes_pending_and_execs` (FakeExec records `--resume`), `test_resume_consumes_pending_once`, `test_leftover_pending_is_not_replayed_without_flag` (start without `--resume` → `read_pending` returns it, runner does nothing), `test_uninstall_adds_to_skip_list`.
- [ ] **Step 2:** implement; PASS. Known-bad: make `ok` follow the exit code → `test_ok_from_reread_not_exit_code` RED. Commit.

## Task 6: Menu-spec v1 + legacy fallback

**Files:** Create `docs/menu-spec.md`, `get_haiggoh_tui/menuspec.py`, `tests/tui/test_menuspec.py`, `tests/tui/fixtures/menu-spec-valid.json`, `…/menu-spec-bad-*.json`.

The contract Plan 3 implements in each repo (*decision*):
```json
{"menu_spec": 1, "title": "…", "actions": [
  {"label": "…", "argv": ["cost-tracker", "cap", "{amount}"], "output": "panel" | "terminal",
   "prompts": [{"id": "amount", "question": "…", "type": "choice" | "text" | "confirm",
                "choices": [{"value": "…", "label": "…"}], "default": null, "pattern": null}]}]}
```
`output: "terminal"` is the escape hatch for an action that must own the TTY.

**Interfaces — Produces:**
- `validate(spec: dict) -> list[str]` (empty = valid; unknown `menu_spec` version, a `{placeholder}` with no prompt, a prompt with no placeholder, choice without choices → errors)
- `build_argv(action: dict, answers: dict[str, str]) -> list[str]` (substitutes whole-token placeholders only; never shell-joins)
- `menu_for(row: Row, run=subprocess.run) -> tuple[Literal["spec","legacy","none"], dict | list[str] | None]` — `spec` only if `row.installed` ≥ `menu.spec_min_version` (non-null) AND `--menu-spec` returns valid JSON within 5 s; otherwise `legacy` with `menu.argv` (+ `["--return-to","get-haiggoh"]` only if ≥ `return_to_min_version`); no menu ⇒ `none`.
- `BACK_LABEL = "👨🏻‍💻 Back to Get Haiggoh"`; `actions_with_back(spec) -> list[dict]` appends it last.

- [ ] **Step 1: failing tests** — `test_valid_fixture_passes`, one test per bad fixture, `test_build_argv_no_shell_join` (answer `"a; rm -rf ~"` stays ONE argv element), `test_never_probes_below_min_version` (FakeExec must record ZERO calls when `spec_min_version` is null or higher than installed — Review Focus 1), `test_return_to_only_when_supported`, `test_back_is_last`.
- [ ] **Step 2:** implement; write `docs/menu-spec.md` from the shape above (it is Plan 3's input); PASS. Known-bad: drop the version gate → `test_never_probes_below_min_version` RED. Commit.

## Task 7: Textual app

**Files:** Create `get_haiggoh_tui/app.py`, `get_haiggoh_tui/screens.py`, `get_haiggoh_tui/theme.tcss`, `tests/tui/test_app_pilot.py`, `tui-requirements.txt`, `tui-dev-requirements.txt` (`pytest`, `pytest-asyncio`).

Layout and copy: exactly the spec's mockup (title, subtitle, summary line `N updates available · M not installed`, two sections, columns Installed/Latest, status `✓` green / newer version / `not installed` / `? unverified`, footer hint line). Info box: port CSL's `#info` CSS (`session_picker.py:801`) and `HoverOptionList` pattern (`session_picker.py:586`) — copied with a comment naming source file + line; follows highlight AND hover. Theme: CSL's ANSI palette and cyan `❯`.

**Interfaces — Consumes:** Tasks 1–6. **Produces:** `GetHaiggohApp(rows_loader=build_rows, runner=run_steps, …)` with injectable collaborators; screens `MainScreen`, `ConfirmScreen` (uninstall: lists each item + its `adds`), `BrewNoticeScreen`, `ProgressScreen`, `ItemMenuScreen`, `PromptDialog`, `ResumeScreen`.

Info box lines: `{mark} {name}` + installed/status; description; `Adds: {adds}`; when not installed, `Installs via {route}` (from `plan_steps` for that row). Single uninstall of get-haiggoh (the only way, Task 3 excludes it from bulk) shows an extra warning screen: `Uninstalling Get Haiggoh removes this manager — you can reinstall it from the haiggoh marketplace.` The 🍺 installer (`INSTALL_ARGV`) always runs under `App.suspend()` — it needs the real terminal for the password — then `verify_installed()` decides what happens next.

Behaviour: paint from `build_rows(cached=True)`, then a worker refreshes with `cached=False` and updates rows + summary (refresh failure → summary shows `couldn't check for updates`). Keys: `space` tick, `enter` open, `a` all, `n` none, `u` update, `i` install, `x` uninstall, `q` quit. Enter: `menu_for` → `spec` ⇒ `ItemMenuScreen` (+ `PromptDialog` per prompt, `output: panel` in `ProgressScreen`, `terminal` via `App.suspend()`); `legacy` ⇒ `App.suspend()` + run argv, return to the same highlighted row; `none` ⇒ focus the info box. First launch ⇒ `mark_first_run_done` after the first paint.

- [ ] **Step 1: failing pilot tests** (venv python; `-rs` so a skip cannot read green) — `test_first_launch_ticks_missing`, `test_summary_counts`, `test_unverified_row_shows_question_mark`, `test_info_box_follows_highlight`, `test_install_button_count_follows_ticks`, `test_brew_notice_shown_only_when_needed`, `test_decline_continues_with_fallback`, `test_uninstall_confirm_lists_adds`, `test_enter_legacy_suspends_and_returns_to_row`, `test_enter_spec_menu_back_is_last`, `test_leftover_pending_shows_resume_screen`, `test_self_single_uninstall_extra_warning`, `test_info_box_shows_route_when_missing`, `test_brew_install_runs_suspended_then_verifies` (fake installer exits 0 but `brew_path` stays None → decline path, not success).
- [ ] **Step 2:** implement; PASS with `~/.local/share/get-haiggoh/tui-venv/bin/python -m pytest tests/tui -rs -q` (0 skipped). Known-bad: break the info-box hover handler → `test_info_box_follows_highlight` RED. Commit.

## Task 8: Bootstrap, launcher, Claude Code entry

**Files:** Create `bin/get-haiggoh-tui`, `bin/get-haiggoh-open-window`, `tests/test_tui_bootstrap.py`. Modify `bin/get-haiggoh` (no-arg TTY → `get-haiggoh-tui`; `GET_HAIGGOH_MENU_SCRIPT` override kept), `skills/get-haiggoh/SKILL.md` (a `/get-haiggoh` with no task ⇒ run `${CLAUDE_PLUGIN_ROOT}/bin/get-haiggoh-open-window`), `README.md`, `CHANGELOG.md`.

**Interfaces:** `get-haiggoh-tui [--help] [--check] [--resume] [--plain]` — `--check` reports venv state and changes nothing; `--plain` execs `get-haiggoh-menu`. Venv: `uv venv` + `uv pip install -r tui-requirements.txt` if `uv` exists, else `python3 -m venv` + pip; stamp `sha256(tui-requirements.txt)` in `<venv>/.req-sha` and rebuild when it differs. Any bootstrap failure ⇒ one stderr line `get-haiggoh: TUI unavailable (<reason>) — opening the plain menu` then exec `get-haiggoh-menu`. `get-haiggoh-open-window`: `osascript` → Terminal.app `do script "<abs path>/bin/get-haiggoh"`; `--help`.

- [ ] **Step 1: failing tests** — `test_help_has_no_side_effects` (temp HOME, assert venv dir absent after `--help`), `test_unknown_flag_exits_2`, `test_invalid_venv_override_aborts_naming_it`, `test_bootstrap_failure_falls_back_to_plain_menu` (fake python that exits 1 → plain menu script executed, stderr line present), `test_req_change_rebuilds`, `test_launcher_no_args_tty_runs_tui` (extend `tests/test_launcher.py`).
- [ ] **Step 2:** implement; run each script's `--help` for real (receipt). Full gate: `pytest -n auto -q` = baseline + new, AND the venv pilot run from Task 7 with 0 skipped. Commit.

## Task 9: Ship 0.10.0 + dogfood

- [ ] **Step 1 (= QC milestone M5, `local:` dispatch, out-of-family reviewer):** final cross-review of `git diff main...feat/tui` + spec. Rebut or fix each finding with evidence.
- [ ] **Step 2:** `rtc-ship.sh` (via run-to-completion:ship) to 0.10.0 — gates, merge, tag, release, plugin refresh. After the tag: `get-haiggoh plan` shows 0.10.0 (re-check once after a minute if not).
- [ ] **Step 3 (dogfood, installed copy):** `get-haiggoh-tui --check` from the installed plugin; then `bin/get-haiggoh-open-window` from the INSTALLED copy and ask the user to confirm on screen: list, statuses, info box, tick counts, Enter on cost-tracker (legacy hand-off and return). Run one real `u` update only if something is genuinely outdated; no installs/uninstalls of real items.
- [ ] **Step 4:** remember entry + waypoint "Plan 3: write the menu-spec adoption plan (contract: docs/menu-spec.md)".

## Side effects

Downloads: venv pins (Task 7/8, allowed). Real `claude plugin`/`brew`: Task 9 Step 3 only. Terminal state: `App.suspend()` hand-offs — pilot-tested with fakes, dogfooded once. Credentials: none. Network in tests: none (monkeypatched; a test that reaches the network is a bug).

## Adversarial review

- Probing every menu with `--menu-spec` → "works" on Textual tools → `backup.sh` writes to a dir named `--menu-spec` → version-gated probe only → `test_never_probes_below_min_version`.
- Pilot tests `importorskip("textual")` under the plain pytest → suite "green" with 11 skips → the TUI is untested → venv run with `-rs`, 0 skipped is the receipt.
- `ok` from exit code → `claude plugin update` exits 0 copying nothing (version-gated) → user told "updated" → re-read state → `test_ok_from_reread_not_exit_code`.
- Self-update execs while steps remain → new process idles → "one keypress" broken → pending file + `--resume` → runner tests.
- Updating `bin/get-haiggoh` but not the SessionStart nudge / skill → two entry points disagree → Task 8 touches launcher, skill and README together; dogfood through each.
- Editing the installed cache to make dogfood pass → reverts on next update → prohibited in the matrix; fix in the worktree, re-ship as 0.10.1.
- Receipts piped through `| tail` hide a non-zero exit → run gates unpiped or check `$pipestatus`.

## Final delivery questions

Implemented vs only planned (Plan 3 is planned only); which receipts ran (paste the result lines); user work preserved (no other repo touched); stopped at the release boundary; blockers stated plainly.
