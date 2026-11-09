# Handoff — execute the get-haiggoh TUI plans (free session, max effort)

## 1. Why this exists

The planning session (Claude Opus 5.5, paid gateway, 2026-11-08) brainstormed the design with the user,
wrote the spec and the plans, and had them approved. The user asked for execution to be handed to a
free session at **max effort**. Nothing has been implemented yet. Do not re-brainstorm or re-plan.

## 2. State (branch `docs/tui-design` of `~/ClaudeWorkspace/get-haiggoh`, local only, not pushed)

- `3246e96` spec: `docs/superpowers/specs/2026-11-08-get-haiggoh-tui-design.md` (approved)
- `fe0daad` + `cffa61e` plans: `docs/superpowers/plans/2026-11-08-tui-00-index.md`, `…-tui-01-get-haiggoh-tui.md`, `…-tui-02-migration-formula.md`
- `1333158` executor "read first" blocks, restated boundaries
- QC playbook: `~/.claude/plans/_PLAYBOOKS/Playbook-milestone-qc-offload-test-proof.md` (commit `7c5d913` in `~/.claude/plans`)
- Gates run so far: none (docs only). Deferred: Plan 3 (written only after Plan 1 ships).

## 3. The goal, verbatim (user, 2026-11-08)

"let's design an interactive textual TUI in the style of CSL for get-haiggoh where all of our claude code
plug-ins are listed and related repos like transcript distiller, Mac Claude migration and human shell are
also listed further down. and each get two separate columns next to it with the installed version number
and a green checkmark (if up to date) or the newer available version listed if not up to date and a not
installed verdict if not installed. Each of those listed should [be] clickable action items that lead into
each of their own interactive menus if they have any or if they're not installed yet should allow
installation. there should also be checkboxes to bulk install or bulk update multiple items at once and a
select all unselect all option" — plus: "I want users who are new to more easily find and manage the
related plug-ins … most users install all of them, but they still should have free choice", "make it
easy to keep everything up-to-date", and the CSL-style info box. Everything decided since is in the spec.

## 4. Standing rules

1. Autonomous: decide and record instead of asking; stop only for forks that cannot be weighed.
2. Adopt the numbered "🚨 read first" block of Plan 1 (and Plan 2's addendum) for the whole session — they
   are part of these rules.
3. **Authority comes from each plan's authority matrix, not from a generic template.** The user approved
   the plans INCLUDING their gated merge/tag/release steps (Plan 2: tap merge + mac-claude-migration
   0.1.5 release; Plan 1: get-haiggoh 0.10.0 release). Each gate needs its receipts first. Nothing
   beyond those boundaries; never force-push or move a tag.
4. Work only in the named worktrees/branches. Never switch the branch of `~/ClaudeWorkspace/get-haiggoh`
   or `~/ClaudeWorkspace/free-agents` (launchers resolve through them).
5. Commit every milestone, staged **by path** (never `git add -A`), with YOUR running model's co-author
   trailer (memory `commit-attribution-by-model`) below the Claude Opus 5.5 line.
6. TDD every change; mutation-check each new guard; never weaken a test to get green.
7. QC milestones (user rule): run /offload at each milestone the plans name, per the playbook — fixtures
   must PROVE the requirement, not go green without it. Check every finding against the real code
   (reviewers hallucinate file names); run every proposed mutation.
8. Resolve model and roster facts when you need them (`free-agent-tool.py --list`), never from memory.
9. Never run `remote-session.sh --stop`, never start another remote session, never kill anything on
   4141–4151 or 8000–8010: one of them is the proxy you run on.
10. Record progress below at every receipt, in the same commit as the work.
11. If you are told to "hand off to a new session", that successor is YOU — continue this handoff.

## 5. Next action

Read the index, then Plan 2 (`2026-11-08-tui-02-migration-formula.md`) top to bottom, and start its Phase 0.

## Progress log (append one line per receipt: date · plan/task · commit · receipt line)

- 2026-11-08 · handoff written · planning session · docs only, no gates run
- 2026-11-08 · Plan 2 Task 1 (tap formula) DONE · homebrew-tap commits a55e904/5d38483/e5e6dc8, PR haiggoh/homebrew-tap#20 merged as c88911a · receipts: known-bad sha → install RED (checksum); install/brew test/audit --strict all exit 0; fresh-shell `mac-claude-backup --help` OK; real run from libexec → meta.env TOOL_VERSION=0.1.4; `bump_formulas.py --dry-run` → "mac-claude-migration: up to date (0.1.4)"; QC validator GPT-OSS-120B via Groq (out-of-family; NVIDIA lanes 429/timeout, z.ai 1113, gemini 503 — routed per user guidance) found R1/R2/R4 WEAK → test block strengthened; mutation battery M1–M10 all RED (M3 green-by-design: Homebrew post-install mode 555); `brew update && brew info haiggoh/tap/mac-claude-migration` → stable 0.1.4; machine left clean (uninstalled, temp tap haiggoh/localtest untapped)
- 2026-11-08 · Plan 2 Task 2 DONE · mac-claude-migration PR #1 merged 4a9bb4f (e1fb066: README brew line, CHANGELOG, VERSION 0.1.5); run-all.sh 68 passed/0 failed; tag v0.1.5 pushed, release published (Latest, 2026-11-08T19:13Z) · bump workflow run 42514684196 success auto-bumped the tap formula 0.1.4→0.1.5 (7ffea7a) — which EXPOSED a pre-existing bump_formulas.py bug: ARCHIVE_URL_RE.sub used group(4)=ver instead of the closing quote → mangled `url "...v0.1.5.tar.gz0.1.4` (invalid Ruby); fixed forward in PR #21 (8ebb6a6, merged 6c0d78f) with a named `quote` group + exact-line regression test, mutation-checked RED→green · final: `brew update && brew install haiggoh/tap/mac-claude-migration` → 0.1.5, fresh-shell both `--help` usage lines OK, `brew upgrade` already current, uninstalled, Cellar clean · Task 3 (route flip in catalog/related-tools.json) DONE inside Plan 1 Task 1 — mac-claude-migration carries `"formula": "haiggoh/tap/mac-claude-migration"` in catalog/related-tools.json, so the route test selects brew for it
- 2026-11-09 · Plan 1 DONE + SHIPPED as get-haiggoh 0.10.0 · feat/tui (18 commits) merged to main, tag v0.10.0 pushed and VISIBLE to installers, release published 2026-11-09T03:48Z, installed plugin refreshed and verified live (`get-haiggoh plan` all current) via rtc-ship exit 0 · receipts: Tasks 1–8 TDD with known-bads; M1–M3 QC validator (Laguna S 2.1 local, out-of-family) all-PROVEN + 10/10 mutations RED; M5 final cross-review found 4 gaps → strengthened (refresh-failure summary, mark in row label/info, self-ticked bulk-uninstall exclusion, tool diagnostic→unverified) + 4 mutations RED; gates: system 236 passed/1 skipped (pilot importorskips off-venv by design), venv tests/tui 82 passed 0 skipped (-rs), rtc-ship --versions-only agree at 0.10.0 · dogfood from installed copy: `get-haiggoh-tui --check` ok (venv ok, req-sha match, textual 3.7.1), `bin/get-haiggoh-open-window` opened the TUI in Terminal (exit 0); no real u update run (nothing outdated) · Plan 3 waypoint added (menu-spec adoption, contract docs/menu-spec.md)
