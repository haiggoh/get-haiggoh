# Changelog

All notable changes to `get-haiggoh` are documented in this file.

## [0.8.0] - 2026-10-03

### Added — PATH shortcuts

- `get-haiggoh apply` (and the new `upgrade` alias) now puts every participating plugin's CLI
  on your shell PATH through version-independent shims in `~/.local/bin`. Plugins opt in with a
  `shortcuts` file at their root (one bare command name per line); get-haiggoh reads it from
  each installed plugin, so no plugin names are hardcoded here.
- `get-haiggoh shims [plan|apply] [--only ..] [--on-collision skip|overwrite|prefix]`. A bare
  `shims` is a dry run.
- A `get-haiggoh` command: no arguments opens the interactive menu, anything else goes to
  `get-haiggoh.py`. Without a terminal, a bare run exits 2 with a usage line instead of crashing.
- The SessionStart hook adds missing, non-colliding shortcuts and names them in its banner.

### Safety

- A name already taken by something that is not a haiggoh shim is **skipped and reported**;
  the report names the alternatives. `overwrite` records the old symlink target (or copies the
  old file) to `~/.local/state/get-haiggoh/shim-backups/` first, and replaces a symlink itself
  rather than writing through it. `prefix` installs `haiggoh-<name>`.
- A shim resolves the plugin from `installed_plugins.json` at run time, falling back to the
  highest numeric version directory, so plugin updates never break it.
- The hook never overwrites or prefixes. `GET_HAIGGOH_NO_SHIMS=1` disables shortcut creation in
  both `apply` and the hook.
- cost-tracker's own `install.sh` treats a haiggoh shim as a foreign file at
  `~/.local/bin/cost-tracker` and replaces it with its checkout link (after backing it up).
  Pick one mechanism per machine.

### Fixed

- `test_hook_never_shells_out_to_git_ls_remote` timed out at 10 s because the hook's daily
  version check made a real HTTP request. The test now skips it, and uses a fake `git` that
  records calls, since an absent `git` could never fail a hook that swallows exceptions.

## [0.7.0] - 2026-09-22

### Documented — the default-branch contract, and where dogfooding goes

`get-haiggoh` pulls every plugin from its repository's **default branch**, and its
outdated-detection reads the `version` in `.claude-plugin/plugin.json` at that branch's
HEAD. It cannot install from a feature branch. That was true before this release and is
now written down as the **contract** rather than left to be discovered: this is a
distribution tool, so what it fetches is defined to be what a consumer gets, and an update
reported from a branch only one person had pushed would describe a state nobody can reach.

The decision this release records is to **keep** that behaviour rather than teach the
catalog `ref`/`sha` pins. A marketplace plugin entry does support them, so this is a
choice, not a limitation. A pin lives in the published `marketplace.json` that every
consumer reads; it keeps resolving successfully after the branch stops mattering, and
removing it depends on someone remembering to. Pinning has one good use — holding
consumers at a known-good version after a bad release — which is deliberate, visible, and
has an obvious removal trigger. Using it to skip a merge trades a one-line merge for
silent, published, mutable state.

Two consequences now stated in both `README.md` and the skill, because both are invisible
from inside a branch:

- **Merging is part of shipping a plugin here.** A change is obtainable only once it is on
  the default branch with its version bumped.
- **A pushed-but-unmerged change makes `plan` correctly say "Nothing to do".** When an
  update is expected and the plan is empty, the likely cause is an unmerged branch, not a
  broken scan. The skill now says so, so that behaviour stops being read as a bug.

**Dogfooding does not require merging first — and the mechanics are now written down,
measured rather than inferred.** Merging *in order to test* makes the default branch the
place unverified work lands, so `README.md` and the skill now carry a step-by-step local
marketplace loop. Three findings drove the rewrite, each verified on a throwaway plugin and
marketplace on Claude Code 2.1.x (created, probed, then removed, with the plugin registries
diffed against a backup to confirm the machine was left unchanged):

1. **A marketplace directory is not the plugin checkout.** It is a separate directory holding
   `.claude-plugin/marketplace.json` whose entry points at the plugin by a `./` relative
   path. `marketplace add` aimed at a plugin repo does not work — a likely first attempt,
   and its failure is what sends people looking for workarounds.
2. **A relative-path source is COPIED into the version-keyed cache, not linked** (verified:
   different inodes). So a source edit does *not* appear in the installed copy, and neither
   `marketplace update` nor `plugin update` brings it over: `plugin update` compares versions
   and prints *"already at the latest version"* while leaving the stale copy in place. All
   three commands exit 0, so nothing reports that the edit did not land. Bumping the dev
   plugin's version does propagate (verified), and running the shipped script straight from
   the checkout is usually the faster loop.
3. **`mode: "link"` on a `command` source does load in place — but cannot be accepted from
   inside a Claude Code session.** The install refuses and directs you to a real terminal,
   because a marketplace-declared command needs human review. Worth knowing, not something
   an agent can set up unattended.

**Both documents now forbid editing `~/.claude/plugins/cache/` to test a change**, which is
the reflex that finding 2 provokes. Measured: a marker hand-written into the cache was gone
after the next `plugin update` — silently, no error. It is derived state, it cannot ship, and
a sandboxed session cannot write there at all (that refusal looks like a filesystem fault and
invites further workarounds). This is written as a prohibition with its reason attached,
because the behaviour it prevents has actually been observed in practice.

`apply` against the merged branch then answers the separate question *does it work the way a
consumer receives it*, through the real fetch and install path. Neither dogfood replaces the
other: only the second catches packaging-only failures.

### Tests

69 → 72. The three new cases pin the contract rather than restating the docs, and each was
mutation-tested: planting a `ref=` branch pin in `plugin_manifest_url` fails two of them
(plus two pre-existing URL tests), and breaking the version comparison fails the third.
One asserts the function's signature, so adding a ref parameter fails with a message
pointing at the docs that would need to change with it.

## [0.6.0] - 2026-09-20

### Fixed — sandbox cache denial detection + actionable hint

When running inside a sandboxed Claude Code session, `get-haiggoh apply` would fail silently with `Operation not permitted` / `permission denied` when trying to write to the plugin cache (`~/.claude/plugins/cache/`). This is a built-in Claude Code protection (`write.denyWithinAllow`), not a filesystem problem — the directory IS writable from an unsandboxed shell.

Added three functions to detect this specific failure mode and provide an actionable workaround:
- `_sandbox_denied()` — detects the characteristic error strings (`operation not permitted`, `permission denied`, `eperm`, `read-only file system`)
- `_cache_is_writable_but_denied()` — probes the cache directory to distinguish sandbox denial from genuine permission issues
- `_explain_if_sandboxed()` — prints a one-line hint: run the command OUTSIDE the sandbox by prefixing with `!` (e.g., `! python get-haiggoh.py apply`)

Integrated into `cmd_apply()` for both install and update failures. A remote session previously burned ~15 tool calls on read-only-filesystem/ACL/SIP theories before the user supplied the workaround; now the cause is named immediately.

## [Unreleased]

## [0.5.2] - 2026-09-16

### Fixed

- **The `0.5.1` mode fix did not actually ship.** `git update-index --chmod=+x` was run, but a later
  `git add -A` (staging the changelog in the same commit) re-read the file from the working tree,
  where the filesystem bit was still `644`, and silently reverted the staged mode. The commit landed,
  the release was cut, and the published tree was still `100644` — the version number said fixed while
  the artifact was unchanged.

  **The lesson, which generalises past this repo:** set the bit on the FILE (`chmod 755`), not only in
  the index. `git update-index --chmod` alone is undone by any subsequent `add` of that path. Verify
  with `git ls-files -s <path>` *after* staging everything else, and confirm the published result with
  `gh api "repos/OWNER/REPO/git/trees/HEAD?recursive=1"` rather than trusting the release.

## [0.5.1] - 2026-09-16

### Fixed

- **`bin/get-haiggoh.py` was committed non-executable (`100644`)**, so the bare `get-haiggoh.py plan`
  form the skill documents failed with `permission denied` on every install — while
  `bin/get-haiggoh-menu` beside it was correctly `100755`. The file has a `#!/usr/bin/env python3`
  shebang and Claude Code puts an enabled plugin's `bin/` on the Bash tool's `PATH`, so it is meant
  to be run directly. Mode changed to `100755`; no content change.

  The failure mode was quietly misleading: `permission denied` (not `command not found`) reads like a
  PATH-shadowing problem, so the obvious diagnosis is wrong. `which -a get-haiggoh.py` also reports
  `not found` in a login shell, because the plugin `bin/` directories are only on the *Bash tool's*
  PATH — which makes the file look absent rather than unexecutable.

## [0.5.0] - 2026-09-15

### Added
- Added `--help` support to `get-haiggoh.py` for proper usage information
- Added `get-haiggoh-menu` - a menu-driven interface for managing plugins
- Default action in menu is to install/update all plugins (press Enter or choose 2)
- Menu provides options to plan/apply all plugins or specific plugins (by name/category)

### Fixed
- Fixed `get-haiggoh.py` to show usage when called without valid arguments instead of exiting silently
- Maintained backward compatibility with existing usage patterns

### Documentation
- Updated README.md with comprehensive usage instructions for both direct and menu-driven interfaces
- Added examples for interactive menu usage