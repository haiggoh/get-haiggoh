# get-haiggoh

Install and keep up to date every published `haiggoh` Claude Code plugin from one place.
Also the canonical home of the `haiggoh` marketplace catalog (`.claude-plugin/marketplace.json`)
-- relocated here from `claude-code-desktop-sync`, which only hosted it because it happened
to be the first plugin published, not because it was the right fit.

## What it does

- **SessionStart hook** (`hooks/check-installed.py`): once per day (throttled via a local
  stamp file, so it doesn't add network latency to every single session), refreshes the
  marketplace catalog and checks for haiggoh plugins that are either not installed or have
  a newer commit upstream than what's installed. If anything's found, it nudges you via
  `additionalContext` toward this plugin's skill. Says nothing if everything's current.
- **Skill** (`get-haiggoh`): triggered by specific phrasing ("install all my haiggoh
  plugins", "get-haiggoh", "sync my haiggoh plugins") -- not a bare generic "install
  everything", which is too easy to misfire on unrelated requests. Shows you a plan
  (what would be installed/updated), asks for confirmation, then executes it.

## MVP scope

Installs/updates **everything** in the catalog, no picking. A curated/categorized mode
(e.g. grouping by purpose) is a natural future extension once the plugin list grows large
enough that "everything" stops being the obviously-right default -- not built in this
version.

## Configuration

- `GET_HAIGGOH_AUTO_UPDATE` (`ask` default | `silent`): `ask` means the SessionStart hook
  only nudges about outdated plugins; `silent` means it runs `claude plugin update` for
  them itself, no prompt. This ONLY affects updates to already-installed plugins --
  brand-new installs always go through the confirming skill, regardless of this setting.
- `~/.claude/.get-haiggoh-skip.json`: per-plugin skip list, `{"<name>": "install"|"update"|"both"}`.
  Managed via the skill when you say "skip that one" in response to a nudge.

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
