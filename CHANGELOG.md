# Changelog

All notable changes to `get-haiggoh` are documented in this file.

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