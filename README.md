# get-haiggoh

Install and keep up to date every published `haiggoh` Claude Code plugin from one place.
Also the canonical home of the `haiggoh` marketplace catalog (`.claude-plugin/marketplace.json`)
-- relocated here from `claude-code-desktop-sync`, which only hosted it because it happened
to be the first plugin published, not because it was the right fit.

## Install

```
/plugin marketplace add haiggoh/get-haiggoh
/plugin install get-haiggoh@haiggoh
```

## What it does

- **SessionStart hook** (`hooks/check-installed.py`): once per day (throttled via a local
  stamp file, so it doesn't add network latency to every single session), refreshes the
  marketplace catalog and checks for haiggoh plugins that aren't installed at all. If
  anything's missing, it nudges you via `additionalContext` toward this plugin's skill.
  Says nothing if everything's installed. Version-drift (outdated) detection runs at boot
  too, but the network sweep behind it is paid **at most once a day**: the fetched versions
  are cached next to the throttle stamp, so every later session that day compares against
  the cache with no network hit. `bin/get-haiggoh.py plan` always checks live.
- **Skill** (`get-haiggoh`): triggered by specific phrasing ("install all my haiggoh
  plugins", "get-haiggoh", "sync my haiggoh plugins") -- not a bare generic "install
  everything", which is too easy to misfire on unrelated requests. Shows you a plan
  (what would be installed/updated, missing AND outdated), asks for confirmation, then
  executes it.

## How "outdated" is decided

get-haiggoh compares **versions**, not commit shas: the installed version from
`~/.claude/plugins/installed_plugins.json` against the `version` in the repo's own
`.claude-plugin/plugin.json` at `HEAD` (one fetch per plugin, the same cost as the
`git ls-remote` it replaced).

It used to compare `gitCommitSha` against remote `HEAD`, and that field is written once at
first install and **never rewritten** -- one plugin here still recorded its initial commit
across three version bumps. Measured on 2026-08-30 across 11 installed plugins: `version`
and `installPath` were accurate in 11/11 cases, `gitCommitSha` in none of the updated ones.
The result was a phantom "update available" for 9 of 9 plugins that were already current, at
which point a real pending update was indistinguishable from the noise.

Two consequences worth knowing:

- **A push that does not bump `plugin.json` is not reported.** The install path is keyed on
  the version (`~/.claude/plugins/cache/<owner>/<name>/<version>/`), so an update with no
  version bump has nowhere new to land and `claude plugin update` leaves the existing
  directory untouched. Nagging about it could never be satisfied. Bump the version when you
  publish -- which is the convention these plugins already follow.
- **`apply` verifies by outcome.** `claude plugin update` exits 0 for "the clone succeeded",
  which is not the same as "this machine now runs that code", so `apply` re-reads the
  recorded version afterwards and reports `ok (0.5.1 -> 0.6.0)` or `NOT APPLIED (exited 0
  but still 0.5.1, expected 0.6.0)` -- and counts the latter as a failure.

A failed or timed-out fetch, or a plugin with no recorded version, falls **silent** rather
than guessing: an unknown never becomes an "update available".

## Selective install/update

`bin/get-haiggoh.py plan|apply` accepts:

- `--only name1,name2` -- restrict to specific plugin names (exact match; typos silently
  yield an empty selection rather than erroring, matching this tool's fail-safe style).
- `--category NAME` -- restrict to catalog entries whose marketplace.json `category`
  field equals `NAME`. Both flags AND together when given.

**Known limitation:** every plugin in the current catalog is tagged `category:
"productivity"`, so `--category` doesn't discriminate yet -- there's no real taxonomy
behind it today. Diversifying the categories is a separate, more consequential edit to
the shared `marketplace.json` (affects every installed plugin's metadata) and deserves
its own review rather than being folded silently into this feature. `--only` is fully
functional today; `--category` is the mechanism, ready for whenever the taxonomy exists.

## Configuration

- `~/.claude/.get-haiggoh-skip.json`: per-plugin skip list, `{"<name>": "install"|"update"|"both"}`.
  Managed via the skill when you say "skip that one" in response to a nudge.

Installs and updates always go through the confirming skill -- the SessionStart hook only
ever nudges, it never runs `claude plugin install/update` itself.

## Known limitation

A brand-new user still has to manually run `claude plugin marketplace add
haiggoh/get-haiggoh` and `claude plugin install get-haiggoh@haiggoh` once, by hand -- this
plugin can't bootstrap its own first install. Everything after that first install is
automated.

## Tests

```bash
pip install pytest  # or pipx install pytest
pytest -v
```
