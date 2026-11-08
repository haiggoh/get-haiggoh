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
