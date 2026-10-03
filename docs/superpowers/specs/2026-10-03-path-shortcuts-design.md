# PATH shortcuts for haiggoh plugin CLIs — design

Date: 2026-10-03 · Branch: `feature/path-shortcuts` (worktree `~/ClaudeWorkspace/get-haiggoh-shortcuts`)

## Intent

The user wants to type `get-haiggoh upgrade`, `waypoints`, etc. in a normal terminal. Claude Code only
puts a plugin's `bin/` on the **Bash tool's** PATH, pinned to a version directory, so none of these work
in the user's own shell. Success: after `get-haiggoh apply` (or `upgrade`), every participating plugin's
CLI is reachable by bare name, keeps working across plugin updates, and nothing already on PATH is
overwritten without consent.

Stated by the user: `upgrade` is a new alias of `apply`; a bare `get-haiggoh` opens the interactive menu;
shortcuts are created by default on install; for THIS machine the `agy-*` symlinks of `waypoints`,
`interrupted`, `lasting-plans`, `cost-tracker` should be overwritten (the haiggoh plugins take
precedence); for other users the default is skip-and-report with overwrite/prefix offered.

Assumptions (not yet confirmed): bare runs of other tools keep their current behavior (waypoints already
opens a selector on a TTY; the others print a report); the SessionStart hook may add non-colliding shims.

## Out of scope

- **free-agents is not touched** (repo is mid-merge across working trees, user instruction 2026-10-03).
  No `shortcuts` file is added there, and the `csl` / `agy-csl` link is left as is. Adding it later is a
  one-line change in that repo once the merge settles.
- `lowkey`, `lk`, `local-agent` (they point at the local-agents checkout, not a plugin).
- New menus for `interrupted`, `lasting-plans`, `cost-tracker`.

## Design

### 1. Declaration — `shortcuts` file per plugin
A plain-text file at the plugin root, one command name per line (`#` comments allowed). The name must
exist as an executable in that plugin's `bin/`. get-haiggoh discovers participants by reading the
`shortcuts` file of each INSTALLED plugin, so no roster is hardcoded in get-haiggoh.
Initial participants: get-haiggoh (`get-haiggoh`), waypoints (`waypoints`), resume-interrupted
(`interrupted`), lasting-plans (`lasting-plans`), cost-tracker (`cost-tracker`).

### 2. Shim — version-independent launcher
`~/.local/bin/<name>` is a small bash script (marked with a `# haiggoh-shim` line so it is recognisable
as ours). At run time it:
1. reads `~/.claude/plugins/installed_plugins.json` and takes `installPath` for `<plugin>@haiggoh`;
2. falls back to the highest version directory under `cache/haiggoh/<plugin>/` if the record is missing;
3. `exec`s `<installPath>/bin/<name> "$@"`; if nothing resolves it exits 127 with a one-line message.

The installed record is authoritative: the cache can hold stale directories (get-haiggoh has `0.5.2`,
`0.7.0` and `1.0.0` while 0.7.0 is recorded), so a directory sort alone could pick the wrong copy.

### 3. The `get-haiggoh` command
New launcher `bin/get-haiggoh`:
- no arguments → `get-haiggoh-menu`;
- `plan`, `apply`, `upgrade` (alias of `apply`), `shims` → `get-haiggoh.py`;
- `--help` works, and an unknown argument exits non-zero with a usage line on stderr.
`get-haiggoh.py` gains `upgrade` and `shims [plan|apply]`. The menu keeps working unchanged.

### 4. Default-on
`apply`/`upgrade` runs the shim step after installs and updates. The SessionStart hook adds missing shims
that do not collide and reports them in its existing nudge; it never touches a collision.

### 5. Collisions
For each wanted name, inspect `~/.local/bin/<name>` (and any other PATH hit):
| State | Action |
|---|---|
| absent | create shim |
| our shim | refresh if stale |
| anything else | per `--on-collision`: `skip` (default, reported with the alternatives), `overwrite`, `prefix` (`haiggoh-<name>`) |
`overwrite` first records the previous link target or file in `~/.local/state/get-haiggoh/shim-backups/`
with a timestamp, so it is reversible. Regular files are copied, not discarded. File modes are preserved
or set to 755 for new shims. For this machine, `overwrite` is run once for the four `agy-*` links.

### 6. Tests, docs, release
Tests (in `tests/`) must cover the SUCCESS branch: shim created and actually executes the plugin;
resolution after a simulated version bump; each collision policy; backup written on overwrite; stale
cache directory ignored in favour of the installed record; `upgrade` equals `apply`; bare `get-haiggoh`
reaches the menu. Mutation-check the resolution test. Bump version in manifest, CHANGELOG and README
together (0.8.0). Work stays on the branch until the user approves merging.

## Open questions
1. The other participating plugins each need a `shortcuts` file (small PRs in their own repos). Confirm
   that touching waypoints, resume-interrupted, lasting-plans and cost-tracker repos is fine, since each
   also needs a version bump to reach the installed cache.
2. Whether the hook-side auto-add (section 4) is wanted or `shims` should be explicit only.
