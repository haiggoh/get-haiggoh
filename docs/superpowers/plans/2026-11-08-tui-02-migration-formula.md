# mac-claude-migration 🍺 formula Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (native: the executor does every task, then one final review). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `brew install haiggoh/tap/mac-claude-migration` installs working `mac-claude-backup` / `mac-claude-restore` commands, kept current by the tap's existing auto-bump workflow.

**Architecture:** One new formula in `homebrew-tap/Formula/`, pointing at the existing `v0.1.4` tag source archive. The tap's hourly `.github/workflows/bump-formulas.yml` repoints any tag-archive formula at the newest release, so no per-release manual step. The mac-claude-migration README gains the brew line.

**Tech Stack:** Homebrew Ruby formula, zsh/bash scripts.

**Spec:** `docs/superpowers/specs/2026-11-08-get-haiggoh-tui-design.md` § "Prerequisite — mac-claude-migration 🍺 formula".

## 🚨 System instructions for the executor — read first

1. Self-contained: no chat history. The same 12 standing rules as Plan 1's "read first" block apply here (`2026-11-08-tui-01-get-haiggoh-tui.md`) — read them now; rules 3 and 4 are replaced by 2 and 3 below.
2. This plan runs FIRST. Work on feature branches in homebrew-tap and mac-claude-migration only; no worktree is needed in these two repos unless Phase 0 finds dirty files (then stop and report).
3. Task 3 edits get-haiggoh only after Plan 1 Task 1 exists — otherwise record it as deferred.
4. Highest boundary: **merge of the tap formula + release of mac-claude-migration 0.1.5.** Leave this Mac with no stray brew install of the formula.

## Global Constraints

- Formula url form: `https://github.com/haiggoh/mac-claude-migration/archive/refs/tags/v<VER>.tar.gz` (the form `bump_formulas.py` recognises — *confirmed live* in `homebrew-tap/README.md` § Automatic formula updates).
- sha256 computed from the downloaded file, never typed.
- Command names (*decision*): `mac-claude-backup` → `backup.sh`, `mac-claude-restore` → `restore.sh`.
- `depends_on :macos`. No other dependency unless Phase 0 finds one.

## Quality-control milestone (standing rule — user, 2026-11-08)

Procedure: `~/.claude/plans/_PLAYBOOKS/Playbook-milestone-qc-offload-test-proof.md`. **After Task 1
Step 6 (before merging the tap PR), run /offload with that playbook's brief: attach the formula, its
`test do` block, and the Step 4–6 receipts. The question is whether `brew test` actually proves the
installed commands work from the formula's install location (not from the checkout), and whether the
url form really is the one the auto-bump recognises. Run every proposed mutation; fix or rebut with
evidence before merging.**

## Authority matrix

| Operation | Authority |
|---|---|
| Edit + local commit in homebrew-tap and mac-claude-migration on a feature branch | allowed now |
| `brew install --build-from-source ./Formula/…`, `brew test`, `brew audit` locally | allowed now |
| Push the tap branch, merge to tap `main` | allowed after Task 1 receipts are green (the user approved the plan, which includes shipping) |
| mac-claude-migration README change: bump 0.1.5, ship via its `rtc-ship.sh` (merge, tag, release) | allowed after Task 2 receipts green |
| Force-push, moving a published tag, editing any installed copy under `$(brew --prefix)` | **prohibited** |

Highest granted boundary: **release of mac-claude-migration 0.1.5 and merge of the tap formula.**

## Phase 0 — preflight (read-only)

- [ ] Write three sentences connecting Task 1 to "a newcomer gets mac-claude-migration via brew from the get-haiggoh TUI".
- [ ] `git -C ~/ClaudeWorkspace/homebrew-tap status --porcelain` and same for mac-claude-migration — any output ⇒ stop and report (not your work).
- [ ] *Unknown to inspect:* do `backup.sh`/`restore.sh` resolve sibling files relative to their own path (run `tests/test_portability.sh`)? If they assume a writable checkout, the formula must install to `libexec` and exec from there — record the finding.
- [ ] Baseline: `cd ~/ClaudeWorkspace/mac-claude-migration && ./tests/run-all.sh` → record pass count.

## Task 1: Formula

**Files:** Create `homebrew-tap/Formula/mac-claude-migration.rb`

- [ ] **Step 1:** branch `feat/mac-claude-migration-formula` in homebrew-tap.
- [ ] **Step 2:** write the formula: `libexec.install Dir["*"]`; `bin.write_exec_script` (or a wrapper) for the two commands; `test do` runs `mac-claude-backup --help` and asserts its usage line (copy the exact first line from `./backup.sh --help`).
- [ ] **Step 3:** sha: `curl -fsSL <url> | shasum -a 256` → paste into the formula.
- [ ] **Step 4 (known-bad first):** set the sha to 64 zeros → `brew install --build-from-source ./Formula/mac-claude-migration.rb` must FAIL with a checksum mismatch. Restore the real sha.
- [ ] **Step 5 (receipt):** `brew install --build-from-source ./Formula/mac-claude-migration.rb && brew test mac-claude-migration && brew audit --strict --formula ./Formula/mac-claude-migration.rb`; then `mac-claude-backup --help` from a fresh shell prints the usage line. Record exits.
- [ ] **Step 6 (receipt):** `python3 .github/scripts/bump_formulas.py --dry-run` lists mac-claude-migration as recognised (proves the auto-bump will cover it).
- [ ] **Step 7:** `brew uninstall mac-claude-migration` (leave the machine as found), commit by path, push, merge to tap `main` via a PR; after merge `brew update && brew info haiggoh/tap/mac-claude-migration` shows 0.1.4.

## Task 2: mac-claude-migration README + release 0.1.5

- [ ] **Step 1:** branch in mac-claude-migration; README install section gains `brew install haiggoh/tap/mac-claude-migration` above `./backup.sh`, naming the two commands.
- [ ] **Step 2:** `./tests/run-all.sh` = baseline count; CHANGELOG entry; ship with that repo's `rtc-ship.sh` (bumps VERSION 0.1.5, merge, tag, release).
- [ ] **Step 3 (receipt):** within the hour (or `gh workflow run bump-formulas.yml -R haiggoh/homebrew-tap -f formula=mac-claude-migration`) the tap formula url says `v0.1.5`; `brew upgrade mac-claude-migration` after a reinstall reaches 0.1.5. Uninstall again afterwards.

## Task 3: get-haiggoh route flip (only after Plan 1 Task 1 exists)

- [ ] In `catalog/related-tools.json` (Plan 1), set mac-claude-migration `"formula": "haiggoh/tap/mac-claude-migration"`; the route test from Plan 1 Task 3 now selects brew for it. Commit with Plan 1's next ship.

## Adversarial review

- Typing the sha from memory → install "works" from cache → wrong artifact shipped → sha only from `shasum` output → Step 4 known-bad.
- Testing against the local checkout instead of the archive → passes, real install lacks a file → install only via the formula url → Step 5 from a fresh shell.
- Url not in the bump-recognised form → formula silently stays on 0.1.4 forever → Step 6 dry-run receipt.

## Final delivery questions

Highest granted boundary (restated): **merge of the tap formula + release of mac-claude-migration 0.1.5.**
Implemented vs planned; which receipts ran (paste them) and which did not; machine left with no stray brew install; stopped at the authority boundary; plan reread from disk before reporting.
