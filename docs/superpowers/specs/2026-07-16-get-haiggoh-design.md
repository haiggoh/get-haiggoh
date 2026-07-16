# get-haiggoh — design spec

**Date:** 2026-07-16
**Status:** approved (pending spec self-review + user sign-off on the written doc)

## Purpose

A new Claude Code plugin, `get-haiggoh`, that:

1. Becomes the new canonical home for the `haiggoh` marketplace catalog
   (`marketplace.json`), relocated from `claude-code-desktop-sync` (which only hosted
   it because it happened to be the first plugin published — not because it's the
   right fit).
2. Is a one-stop installer/updater for every other published `haiggoh` plugin — "get
   everything I've published, in one place."

Picked over the alternative ("don't relocate the source, install-only") because the
relocation cost is low (solo-developer marketplace, no third-party consumers to
break) once the source re-pointing step below is done explicitly, and a mis-homed
catalog is exactly the kind of "happened by accident" artifact worth fixing while
building the tool that's meant to be its natural home.

## MVP scope

- Installs **all** plugins currently in the marketplace, unconditionally — no
  curated/categorized subset selection in this version.
- **Documented future extension** (README, not built now): categorized/grouped
  install (e.g. "session-continuity" vs "automation-safety" groups) once the plugin
  list grows large enough that install-everything stops being the obviously-right
  default.

## Repo & shape

New public repo `haiggoh/get-haiggoh`, mirroring the existing plugin shape used by
`waypoints` / `resume-interrupted` / `measure-twice`:

```
.claude-plugin/plugin.json       # name, version, author, license, homepage — NO "hooks" key
.claude-plugin/marketplace.json  # RELOCATED HERE — the new canonical catalog
hooks/hooks.json                 # SessionStart, matcher "startup"
hooks/check-installed.py         # the nudge hook (stdlib-only Python)
skills/get-haiggoh/SKILL.md
tests/test_get_haiggoh.py        # pytest, stdlib-only, mocked CLI calls
README.md
LICENSE
.gitignore                       # __pycache__/, .DS_Store
```

`get-haiggoh`'s own entry lives in `marketplace.json` like every other plugin
(`source: {source: url, url: "https://github.com/haiggoh/get-haiggoh.git"}`), so a
brand-new user installs it the same way as anything else — see "Known limitation"
below for the one thing that can't be automated away.

## Marketplace relocation — migration steps

`~/.claude/plugins/known_marketplaces.json` pins the `haiggoh` marketplace's source
repo to `claude-code-desktop-sync`. Moving `marketplace.json` out of that repo with no
redirect breaks `marketplace update haiggoh` for this machine (and any other machine
running these plugins) — the *file move* alone isn't the whole migration. Steps, in
order:

1. Push `get-haiggoh` (with `marketplace.json` inside it) to GitHub.
2. On each machine: `claude plugin marketplace remove haiggoh` then
   `claude plugin marketplace add haiggoh/get-haiggoh` — re-points the local
   registration's source repo.
3. Remove `marketplace.json` from `claude-code-desktop-sync` (clean cut-over, no
   redirect stub left behind — this is a solo/personal marketplace, there's no
   third-party consumer relying on the old location).
4. Update the `claude-code-desktop-sync` README / any docs that reference
   marketplace.json's old location.
5. Update memory (`plugin-publishing-workflow`, `waypoints-project`,
   `resume-interrupted-project`, etc.) wherever the old location is cited as fact.

## Skill (`get-haiggoh`)

- **Trigger wording is specific**, not a bare generic phrase: "install all my haiggoh
  plugins", "get-haiggoh", "sync my haiggoh plugins". Deliberately avoids a bare
  "install everything" trigger, which is too likely to misfire in unrelated
  conversations about installing other, unrelated software.
- **Procedure when invoked:**
  1. Run `claude plugin marketplace update haiggoh` (refresh the catalog).
  2. Read the marketplace-repo copy of `marketplace.json` — resolved via
     `known_marketplaces.json`'s `installLocation` for the `haiggoh` entry, **never**
     `$CLAUDE_PLUGIN_ROOT/marketplace.json` (that's get-haiggoh's own frozen,
     version-pinned install copy, which goes stale the moment a newer version is
     published upstream — see the hook section for why this distinction matters).
  3. Read `~/.claude/plugins/installed_plugins.json` for what's actually installed,
     and at what version.
  4. Compute two sets: **missing** (in catalog, not installed) and **outdated**
     (installed at a version below the catalog's), excluding `get-haiggoh` itself
     from both.
  5. **Present the plan and ask for confirmation** before running anything — this is
     a visible/effectful action (installs/updates change local plugin state), so it
     follows the standing confirm-before-visible-changes rule regardless of the
     hook's own auto-update setting.
  6. On confirmation, run `claude plugin install <name>@haiggoh` for each missing
     plugin and `claude plugin update <name>@haiggoh` for each outdated one; report a
     summary (installed / updated / already current / failed, with real error text
     surfaced directly — a human is present to react, unlike the hook).

## SessionStart hook (`check-installed.py`)

- **Throttled network refresh:** a stamp file (e.g.
  `~/.claude/.get-haiggoh-last-refresh`) gates the `marketplace update haiggoh` call
  to once per day — with 7+ other haiggoh SessionStart hooks already running on every
  session start, an unconditional network pull here adds latency/network dependency
  to every single session for marginal freshness gain. The subprocess call itself has
  a short timeout (~5s); on timeout, non-zero exit, or "already refreshed today", the
  hook skips the diff entirely for that session rather than diffing against
  potentially-stale data pretending it's fresh.
- **Reads the marketplace-repo copy**, same resolution as the skill (via
  `known_marketplaces.json`'s `installLocation`) — not its own bundled copy.
- **Diffs on two axes** (missing, outdated) against a skip-list file
  (`~/.claude/.get-haiggoh-skip.json`), entries keyed by plugin name with a `scope`
  field: `install`, `update`, or `both`. A "skip this one" response during a
  *new-install* nudge writes `install`; during an *outdated* nudge (in `ask` mode)
  writes `update`. This lets "don't bother me about installing X" and "don't
  auto-update X for now, but yes it's fine to have it installed" coexist as distinct,
  independently-settable states for the same plugin.
- **Configurable update behavior** via `GET_HAIGGOH_AUTO_UPDATE` env var:
  - `ask` (default) — hook only nudges (`additionalContext`) toward outdated
    plugins; no state changes.
  - `silent` — hook runs `claude plugin update <name>@haiggoh` itself for each
    outdated plugin not on the `update`/`both` skip-list, no prompt.
  - This env var **only** gates updates to already-installed plugins. Brand-new
    installs are never silent — they always route through the confirming skill,
    regardless of this setting.
- **Fail-safe throughout:** any error (malformed JSON, missing files, `claude` CLI
  not on PATH, subprocess timeout) → exit 0, no banner, never blocks a session —
  matching every sibling plugin's hook contract. No banner at all if there's nothing
  to report (missing+outdated sets both empty after skip-list filtering).

## Known limitation (documented, not solved)

A brand-new user still has to manually do
`claude plugin marketplace add haiggoh/get-haiggoh` and
`claude plugin install get-haiggoh@haiggoh` **once**, by hand — get-haiggoh cannot
bootstrap its own first install. Everything after that first install is automated.
This gets one clear paragraph in the README, not engineered around.

## Testing

- pytest, stdlib-only (mirrors `waypoints`/`resume-interrupted`).
- **Diff logic** (pure functions, no subprocess/network): unit tests for
  missing/outdated computation, self-exclusion, and skip-list filtering by scope
  (`install` vs `update` vs `both`), using synthetic `marketplace.json` /
  `installed_plugins.json` fixtures.
- **Marketplace-copy resolution:** a fixture where the bundled
  `$CLAUDE_PLUGIN_ROOT` copy and the marketplace-repo copy disagree (different plugin
  lists/versions) — assert the code reads the marketplace-repo copy, not the bundled
  one.
- **Hook-level tests:** no-banner-when-nothing-to-report; no-banner-on-refresh-timeout
  (asserting the hook skips the diff rather than using stale data silently);
  throttle-stamp respected (second call same day doesn't re-run the network refresh).
- **No live `claude` CLI calls in tests** — `subprocess.run` is mocked/stubbed
  throughout; the skill's actual install/update execution is exercised manually
  (dogfooded), same as every prior plugin's publish checklist.

## Out of scope for this version

- Curated/categorized install groups (documented as a future extension above).
- Any cross-machine sync of the skip-list or refresh-stamp files — both are purely
  local to the machine they run on.
- Auto-installing brand-new plugins silently under any hook setting — always
  confirmed via the skill.
