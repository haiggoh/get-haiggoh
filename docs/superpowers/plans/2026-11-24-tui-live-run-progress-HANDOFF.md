# HANDOFF — get-haiggoh 0.11.0 live run progress → GLM 5.3 Flash (max effort), 2026-11-24

## 1. Why this exists

A paid Opus session wrote and committed the plan, after the user decided its open design questions (2026-11-24, recorded in the plan's "Deviations"). It then ran Phase 0. The user asked for execution to be handed to a free GLM 5.3 Flash session at max effort. Nothing failed; this is a planned handover, not a recovery.

**Relaunch (2026-11-24 ~18:50 CET):** the first GLM session (pid 2065, 15:22) made ZERO progress. Every request returned HTTP 400 (`Unsupported parameter(s): _la_booked_tokens`), a free-agents 0.62.3 proxy bug. That bug is fixed in **free-agents 0.63.1** (verified installed, and the canonical checkout is at `1cb38cb`). The Mac was then rebooted, and that session is gone. It committed nothing: the branch is unchanged at this handoff's commit. You are the fresh successor. Start at §5 exactly as written; nothing from the first attempt needs undoing.

**Relaunch 2 (2026-11-24 ~19:05 CET), now on Mistral Large 4 "Le Chonk":** the second GLM session (pid 27787, 18:48) also made zero progress. This time NVIDIA's `z-ai/glm-5.3-flash` endpoint itself hung: a 16-token request sent DIRECTLY to NVIDIA, without the proxy, got no answer in 90 s, while `mistralai/mistral-large-4-1t-a52b` on the same key answered `200` in under 1 s. The user chose a fresh Le Chonk session. The branch is still unchanged since this handoff; nothing to undo.

## 2. State (verified 2026-11-24 15:2x CET)

- Worktree `~/ClaudeWorkspace/get-haiggoh/.wt/tui-live-run-progress`, branch `feat/tui-live-run-progress`. Clean, and it contains `origin/main` (`a4a0763`). The canonical checkout `~/ClaudeWorkspace/get-haiggoh` is on `main`; leave it there.
- Commits on the branch:
  - `7f46276` the spec
  - `128a2f3` the plan
  - `c6fcc38` the plan with the user's decisions folded in
  - (this handoff's commit)
- **Phase 0 is DONE.** Receipt 0:
  - Baseline 1, `pytest -q -n auto tests -p no:cacheprovider`: `EXIT1:0`, `270 passed, 2 skipped in 9.66s`. The 2 skips are `tests/tui/test_app_pilot.py:17` and `tests/tui/test_tui_0102.py:23`, both `could not import 'textual'`; that is the gap Task 1 closes.
  - Baseline 2, `~/.local/share/get-haiggoh/tui-venv/bin/python -m pytest -q -rs tests/tui -p no:cacheprovider`: `EXIT2:0`, `121 passed in 9.36s`, 0 skipped.
  - Textual 3.7.1 in the TUI venv. `README.md` does not describe the run screen (grep empty), so Task 8 needs no README change.
- No pre-existing failures.

## 3. The goal (verbatim from the user, 2026-11-23)

> the interactive menu of get-haiggoh has an update feature (update then select all and update) but it currently shows now spinner, no progress, no verbose output of what's happening. for all the user knows the app could be wedged and completely frozen since it doesn't accept any clicks while its updating and hover doesn't react. that's a bad user experience, we have to overhaul that system to become a lot more user friendly and responsive. especially when installing multiple it needs to be clearly visible which is currently being installed (spinner and progress bar after the name in the same row …

The full design is in the spec, `docs/superpowers/specs/2026-11-23-get-haiggoh-tui-live-run-progress-design.md`. The plan is the executable form: `docs/superpowers/plans/2026-11-24-tui-live-run-progress.md`. **The plan is authoritative where it deviates from the spec.**

## 4. Standing rules (adopt for the whole session)

1. Autonomous: decide and record instead of asking; stop only for forks that cannot be weighed. Task 9 is the one planned stop: it asks the user.
2. Work only in the worktree above. Never switch the branch of `~/ClaudeWorkspace/get-haiggoh`. Never edit `~/.claude/plugins/cache/**`.
3. Commit every task, staged **by path** (never `git add -A` / `git add .`), and check `git diff --cached --stat` first. Every commit ends with exactly these two trailer lines:
   ```
   Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
   Co-Authored-By: <the trailer of the model YOU run on, from the table below>
   ```
   Check which model you run on (your session banner / window title) and copy its line verbatim; never invent one:
   - Mistral Large 4 "Le Chonk" (`nvidia-mistral-large4`): `Co-Authored-By: Mistral Large 4 "Le Chonk" 1T-A52B <noreply@mistral.ai>`
   - Z.ai GLM 5.3 Flash (`nvidia-glm53`): `Co-Authored-By: GLM 5.3 <noreply@z.ai>` (Flash commits as `GLM 5.3`, by the user's ruling)
   - Any other model: STOP and ask; do not derive a trailer.
4. Push the branch only when the plan says so (end of Task 8). **Never merge, tag, release, run `rtc-ship`, `claude plugin update` or `get-haiggoh apply`.** Those need the user's explicit go at Task 9.
5. TDD every change: write the test, see it fail for the right reason, implement, see it pass. Run every discriminant the plan lists and quote its RED line. Never weaken a test to get green.
6. Pilot tests run ONLY under `~/.local/share/get-haiggoh/tui-venv/bin/python -m pytest … -rs`. A skipped pilot is a failed receipt.
7. Never pipe a test run into `tail`/`head` before reading its exit code. Redirect to a file, `echo EXIT:$?`, then read the file.
8. At each QC milestone (QC-1…QC-4 in the plan), dispatch an independent review with `~/ClaudeWorkspace/free-agents/bin/free-agent-tool.py` (out of family from GLM; attach the files through `"files"`) and check every finding against the real code. Reviewers hallucinate file names and line numbers.
9. Resolve model and roster facts when you need them, from the tools (`free-agent-tool.py --list`, `remote-session.sh --list`), never from memory.
10. Never run `remote-session.sh --stop`, never start another remote session, never kill anything listening on 4141–4151 (one of those is the proxy YOU run on). The only processes you may kill are the test children your own tests spawn.
11. Use the native Read/Edit/Write tools for files. The shell tool is `Bash` (capital B). Edit anchors come from a FRESH Read: whole lines, exact indentation.
12. Never type the home directory out in commands; write `~` or `$HOME`.
13. **Record progress here.** At every task receipt, append one line to §6 and include this file in that task's commit. A kill then loses at most one task.
14. You ARE the successor of this handoff. If you die and a later session reads this, it continues from §5; it does not launch yet another session.
15. Branch push failures: `git 100001` / `gh -26276` under a sandbox are SANDBOX errors, not auth errors; the push may already have succeeded. Check with `git ls-remote`.

## 5. Next action

**Phase 0 and Task 1 are DONE** (Task 1 = `9a808ed`, receipt `80a9b6b`; see §6). Do not redo them. **Start at Task 2** of `docs/superpowers/plans/2026-11-24-tui-live-run-progress.md`. Read the whole plan (and the spec it cites) first. Then run Tasks 2 → 2a → 3 → 4 → 5 → 6 → 7 → 8 in order, then Task 9 Step 1 (ask the user) and STOP there. Before starting Task 2, run `git log --oneline -3` and read §6: if a later task already has a receipt there, continue after the LAST receipt instead (the log, not this paragraph, is the truth about progress).

## 6. Progress log (append one line per receipt: task · commit · pass line · discriminant RED line)

- Phase 0 · (no commit) · `270 passed, 2 skipped` / `121 passed` · n/a — Opus, 2026-11-24
- Task 1 · 9a808ed · gate `EXIT:0`: `274 passed, 2 skipped` (pipx) / `125 passed, 0 skipped` (venv, REQUIRE_TEXTUAL=1) · discriminants RED: `EXIT:4` textual-less pipx names textual; planted skip ⇒ `EXIT:1` "1 skipped" — Le Chonk, 2026-11-24
- Task 2 · 0b7f14a · `24 passed` test_runner.py; full `286 passed, 2 skipped` (pipx) / `137 passed, 0 skipped` (venv) · discriminants RED: after_current-without-name-check ⇒ `EXIT:1` "'skipped' not found … the two-step item finishes"; local-mode-calls-reread ⇒ `EXIT:1` "AssertionError: network sweep" — Le Chonk, 2026-11-24
- Task 2a · 28ab716 · `38 passed` (test_status+test_runner); full `292 passed, 2 skipped` (pipx) / `143 passed, 0 skipped` (venv) · timing `20 rows 0.08s` vs 8.5–11.1 s full sweep · discriminant RED: reread_row→tool_status ⇒ `EXIT:1` AssertionError "reread_row must not call tool_status" — Le Chonk, 2026-11-24
