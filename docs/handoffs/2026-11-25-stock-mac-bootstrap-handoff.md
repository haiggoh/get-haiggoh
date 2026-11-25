# Handoff — get-haiggoh 0.12.0 "works on a stock Mac" (TUI Python + PATH)

## 1. Why this exists
A paid Opus session (2026-11-25) did the diagnosis and Tasks 1-4 of the plan below, then the user
invoked `/free-agents:free-session-handover` to finish on a free lane. Nothing failed; this is a
planned hand-off at a clean seam (everything committed and pushed). Do NOT re-diagnose.

## 2. State (worktree `~/ClaudeWorkspace/get-haiggoh/.wt/tui-venv-python-floor`, branch `fix/tui-venv-python-floor`, pushed)
- `6c74eec` fix(tui): venv built on Python >= 3.10; a venv left on 3.9 is rebuilt (`pyvenv.cfg` check)
- `cccddee` feat(tui): admin-free route — pinned private uv 0.13.9 (hardcoded sha256), curl download, uv-managed CPython
- `1d2f64c` feat(shims): `get_haiggoh_pathrc.py` — fenced PATH block in `~/.zprofile` / first existing bash profile
- `270af48` feat(cli): `shims path [--undo]`; hook + apply call `ensure_on_path`
- `e2bb9a0` test(tui): fake venv carries `pyvenv.cfg` (this was the gate hang)
- `0e64d7b` chore(0.12.0): version, CHANGELOG, README, portable regen, plan
- Gate at `0e64d7b`: `pytest -q -n auto tests` → 354 passed, 4 skipped; TUI pilots
  (`GET_HAIGGOH_REQUIRE_TEXTUAL=1 ~/.local/share/get-haiggoh/tui-venv/bin/python -m pytest -q -rs tests/tui`)
  → 210 passed; `python3 scripts/build-portable.py --check` → clean.
- Stock-Mac dogfood VERIFIED (env -i, PATH=/usr/bin:/bin, driver /usr/bin/python3 3.9.6): private uv
  downloaded + sha-verified, CPython 3.15.2 fetched into the fake home, `get-haiggoh-tui --check` → ok;
  hook added the `.zprofile` block once; a fresh login shell ran `get-haiggoh --help` → EXIT 0.
- Plan: `docs/superpowers/plans/2026-11-25-stock-mac-bootstrap.md`. Ledger (git-ignored):
  `.superpowers/sdd/2026-11-25-stock-mac-bootstrap/progress.md` — Tasks 1-3 complete, Task 4 done
  (rulings recorded there). Task 5 (ship) NOT started.

## 3. The goal, verbatim (user, 2026-11-25)
- "get-haiggoh, installed through the marketplace, falls back to the bash menu rather than textual,
  apparently the dependencies aren't installed, I saw this on my collegues when they tried to set it
  up. can we fix it?"
- "get-haiggoh also needs to be on PATH for them too"
- "make sure it should work with brew if its installed but not be dependent on brew so there has to
  be a python install method that works without granting admin rights and without having brew installed"
- PATH decision (multiple choice): **Add automatically**.
- Ship depth: **yes — all the way: gate, merge, tag v0.12.0, release, refresh** (user said "yes").
- Colleague's Claude feedback (pasted by the user, then "proceed"): "Python version: … never checks
  its version. On a stock Mac that's 3.9 …" (DONE) and **"Error message: the one-line notice that it
  fell back to the plain menu is easy to miss."** (NOT done — Next action A).

## 4. Standing rules
1. Autonomous: decide and record instead of asking; stop only for forks that cannot be weighed.
2. Work only in the worktree above. Never switch the branch of `~/ClaudeWorkspace/get-haiggoh` (the
   canonical checkout; launchers resolve through it). It must stay on `main`.
3. Commit every milestone, staged **by path** (never `git add -A`). Co-author trailers: the
   `Claude Opus 5.5` line AND your running model's line, copied verbatim from the memory file
   `commit-attribution-by-model.md` (read it before EVERY commit; never derive a trailer).
   **Shipping IS authorized for this item only** (user: through merge, tag v0.12.0, GitHub release,
   refresh) — but only via `rtc-ship` (Next action C), never by hand-merging or hand-tagging.
4. TDD every change: watch it fail for the right reason, then pass; never weaken a test to go green.
5. Review with an independent dispatch (`free-agent-tool.py`) and check every finding against the
   real code: reviewers hallucinate file names and lines.
6. Resolve model/roster facts from the tools (`remote-session.sh --list`), never from memory.
7. Never run `remote-session.sh --stop`, never start another remote session, never kill anything on
   ports 4141-4151 or 8000-8010: one of them is the proxy you run on.
8. Append one progress line to §6 of THIS file at each milestone, in the same commit.
9. You ARE the successor. Never launch yet another session to pass this work onward.
10. Code under `bin/`, `hooks/`, `get_haiggoh_*.py` runs on macOS's `/usr/bin/python3` **3.9**: no
    `match`, no `X | Y` annotations. Check: `/usr/bin/python3 -c "import ast;ast.parse(open('<f>').read())"`.
11. Tests must never touch the real `~/.zprofile`, `~/.local/bin` or tools dir: `tests/conftest.py`
    autouse sets `GET_HAIGGOH_NO_PATH_EDIT=1` and tmp dirs — keep it that way.
12. Bound every long test run: `perl -e 'alarm shift; exec @ARGV' 500 <cmd>` (exit 142 = it hung;
    find the test with `-v`, do not just rerun). Full-suite `pytest` with `-n auto` is the PATH
    `pytest` (pipx), NOT `python3 -m pytest` (no xdist there).
13. Never edit `~/.claude/plugins/cache/**` or `installed_plugins.json`; never print process argv.

## 5. Next actions (in order)
**A. Make the fallback reason visible (colleague feedback).** Today `bin/get-haiggoh-tui` writes ONE
stderr line then `exec`s the plain menu, whose banner scrolls it away. Change: `plain_menu(reason=None)`
puts the reason in env `GET_HAIGGOH_TUI_FALLBACK_REASON` before the exec; `bin/get-haiggoh-menu` prints
it right under its banner as `⚠️ TUI unavailable: <reason>` plus `   details: get-haiggoh-tui --check`.
Keep the stderr line. Tests first: in `tests/test_tui_bootstrap.py` extend
`test_bootstrap_failure_falls_back_to_plain_menu` with a stub menu that prints the env var and assert
the reason arrives; add a menu test (find how existing tests drive `get-haiggoh-menu` — grep tests/
for `get-haiggoh-menu`) asserting the line appears and is absent when the var is unset. Document the
var in both scripts' `--help` (run `--help` to verify). CHANGELOG 0.12.0 gets one bullet. Re-run
`python3 scripts/build-portable.py` and commit its output. Commit `feat(tui): the plain menu says why
the TUI is unavailable`.

**B. Final whole-branch review.** `git diff c84cda0..HEAD > /tmp/gh-branch.diff`; dispatch it with
`free-agent-tool.py` (prompt: review for correctness bugs, Python-3.9 incompatibility, shell-rc
safety, checksum/download safety; list file:line). Verify each finding in the code; fix real ones TDD,
record rejected ones with a reason in §6. Then the full gate (rule 12) — both halves green.

**C. Ship v0.12.0.** Canonical checkout must be on `main` and clean (`git -C ~/ClaudeWorkspace/get-haiggoh
status --short --branch`; the untracked `.wt/` is fine). Find rtc-ship in the run-to-completion plugin
cache (`ls ~/.claude/plugins/cache/haiggoh/run-to-completion/*/bin/rtc-ship.sh | sort -V | tail -1`)
and run it as `<that path> ~/ClaudeWorkspace/get-haiggoh/.wt/tui-venv-python-floor 0.12.0 "get-haiggoh
works on a stock Mac: TUI Python without brew/admin, get-haiggoh on PATH"` (bare call = usage, exit 2,
ships nothing). A successful ship REAPS the worktree — afterwards use `git -C ~/ClaudeWorkspace/get-haiggoh`.
Before it reaps, copy this file's §6 progress into the commit (it is committed, so it survives).
Verify by outcome: `git -C ~/ClaudeWorkspace/get-haiggoh ls-remote origin refs/tags/v0.12.0`,
`gh release view v0.12.0 -R haiggoh/get-haiggoh`, `get-haiggoh plan` shows get-haiggoh current at
0.12.0 (else `claude plugin marketplace update haiggoh && claude plugin update get-haiggoh@haiggoh`).

**D. Dogfood the INSTALLED copy** (not the checkout): `get-haiggoh-tui --check` from the installed
plugin's `bin/`, `get-haiggoh shims path`, and `get-haiggoh --help | grep 'shims path'`. Report
verified vs assumed. Then tell the user to RESTART Claude Code so the new hook loads, and that
colleagues get it via `get-haiggoh` / `/get-haiggoh` (update) — no manual venv or brew step.

## 6. Progress log (append one line per milestone)
- 2026-11-25 paid session: Tasks 1-4 done, gate green, pushed `0e64d7b`; handed off for A-D.
- 2026-11-25 free session (Mistral Large 4 "Le Chonk", proxy-4150): Next action A done —
  a bootstrap failure now passes its reason to the plain menu via
  `GET_HAIGGOH_TUI_FALLBACK_REASON` (`plain_menu(reason=…)` in `bin/get-haiggoh-tui`) and
  `bin/get-haiggoh-menu` prints `⚠️ TUI unavailable: <reason>` + `details:
  get-haiggoh-tui --check` right under its banner; the stderr line is kept. Tests written
  first and watched RED, then green (test_tui_bootstrap fallback test extended with a
  stub menu printing the env var; new FallbackNoticeTests in test_branding.py cover
  notice-present and notice-absent); both scripts parse on /usr/bin/python3 3.9.6 and
  document the var in --help (verified by running it); live menu run shows the notice;
  CHANGELOG 0.12.0 bullet added; `build-portable.py` regen committed, `--check` clean.
  Next: B (whole-branch review dispatch + full gate), C (rtc-ship v0.12.0), D (dogfood the
  installed copy).
- 2026-11-25 free session (Le Chonk), user follow-up "corporate wifi out of the box":
  truststore was ALREADY folded in (core `_inject_truststore` + curl fallback +
  `UV_SYSTEM_CERTS`/`UV_NATIVE_TLS` + `truststore` pin in the TUI venv + system curl for the
  uv download) — no change. The IPv6-blackhole fix was NOT: `fetch_url`'s urllib attempt used
  stock DNS order. Folded in free-agents' `remote_http.py` fix as `_ipv4_first()`
  (IPv4-first interleaved getaddrinfo, restored even on exception) around the urllib call;
  4 new tests in test_fetch_and_unverified.py watched RED (behavioral one failed with
  "SYN_SENT to a black-holed IPv6 address — full timeout spent"), then 16/16 green;
  get_haiggoh_core.py parses on 3.9.6; portable regen committed, `--check` clean; CHANGELOG
  0.12.0 bullet added.
- 2026-11-25 free session (Le Chonk): B done — whole-branch diff (c84cda0..HEAD) dispatched to
  an out-of-family validator via free-agent-tool.py (KAT Coder V2.5, local kwaipilot family;
  laguna/gemini/step5 routes failed first: RAM preflight, 503, no-reason) → verdict "no
  findings"; every claim it cited was re-checked against the real code and none survived as
  actionable, so nothing to fix and no rejections to record. Own verification sweep: every
  bin/, hooks/, get_haiggoh_*.py parses on /usr/bin/python3 3.9.6 and no 3.10+ syntax is
  present. Full gate at c7cfb67 green on both halves: `pytest -q -n auto tests` → 360 passed,
  4 skipped; TUI pilots under the venv → 210 passed; `build-portable.py --check` → clean.
  Next: C (rtc-ship v0.12.0), D (dogfood the installed copy).
