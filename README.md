# get-haiggoh

Install and keep up to date every published `haiggoh` Claude Code plugin from one place.
Also the canonical home of the `haiggoh` marketplace catalog (`.claude-plugin/marketplace.json`)
-- relocated here from `claude-code-desktop-sync`, which only hosted it because it happened
to be the first plugin published, not because it was the right fit.

## What it does

- **SessionStart hook** (`hooks/check-installed.py`): once per day (throttled via a local
  stamp file, so it doesn't add network latency to every single session), refreshes the
  marketplace catalog and checks for haiggoh plugins that aren't installed at all. If
  anything's missing, it nudges you via `additionalContext` toward this plugin's skill.
  Says nothing if everything's installed. **Version-drift (outdated) detection is NOT
  done at boot** -- it needs a `git ls-remote` per installed catalog entry, which is too
  costly to pay every session; run `bin/get-haiggoh.py plan` (or ask the skill to check)
  when you want an up-to-date/outdated report.
- **Skill** (`get-haiggoh`): triggered by specific phrasing ("install all my haiggoh
  plugins", "get-haiggoh", "sync my haiggoh plugins") -- not a bare generic "install
  everything", which is too easy to misfire on unrelated requests. Shows you a plan
  (what would be installed/updated, missing AND outdated), asks for confirmation, then
  executes it.

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
