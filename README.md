# get-haiggoh

CLI tool to manage haiggoh plugins for Claude Code.

## Usage

### Direct Usage
```bash
# See what would be installed/updated (dry run)
./bin/get-haiggoh.py plan

# Actually install/update plugins
./bin/get-haiggoh.py apply

# Limit to specific plugins
./bin/get-haiggoh.py plan --only video-use,waypoints
./bin/get-haiggoh.py apply --only video-use,waypoints

# Limit to specific category
./bin/get-haiggoh.py plan --category utility
./bin/get-haiggoh.py apply --category utility

# Show help
./bin/get-haiggoh.py --help
```

### Menu-Driven Usage
For an interactive menu experience:
```bash
./bin/get-haiggoh-menu
```

The menu-driven interface provides:
- **Default action** (press Enter or choose 2) is to install/update all plugins
- Option 1: Plan all plugins (dry run)
- Option 2: Apply all plugins (install/update) [DEFAULT]
- Option 3: Plan specific plugins (by name or category)
- Option 4: Apply specific plugins (by name or category)
- Option 5: Exit

When choosing specific plugin options, you can enter:
- `--only name1,name2` to limit to specific plugins
- `--category NAME` to limit to plugins in a specific category
- Leave empty (just press Enter) to operate on all plugins

## Examples
```bash
# Interactive menu - install/update all plugins (default)
./bin/get-haiggoh-menu
# Just press Enter at the menu

# Interactive menu - plan specific plugins
./bin/get-haiggoh-menu
# Choose option 3, then enter: --only video-use,waypoints

# Interactive menu - apply updates to utility category
./bin/get-haiggoh-menu
# Choose option 4, then enter: --category utility
```

## What it pulls: the default branch, on purpose

`get-haiggoh` resolves every plugin from its repository's **default branch**, and its
own outdated-detection reads the `version` in `.claude-plugin/plugin.json` at that
branch's HEAD. It cannot install from a feature branch, and that is the contract rather
than a missing feature: this is a *distribution* tool, so what it fetches is defined to
be what any consumer gets. A plan that reported an update available from a branch only
you had pushed would be describing a state nobody else could reach.

Two consequences worth stating, because both are invisible from inside a branch:

- **A pushed branch is not obtainable, so `plan` will not see it.** If you shipped a
  change and `plan` says "Nothing to do", the likely reason is that the change has not
  been merged — not that the scan failed. Merging is therefore a required step of
  shipping any plugin in this marketplace, not an optional tidy-up afterwards.
- **A same-version push is deliberately not reported either.** The install path is keyed
  on the version (`~/.claude/plugins/cache/<owner>/<name>/<version>/`), so an update that
  does not bump `plugin.json` has nowhere new to land.

### Dogfooding before you merge

Merging *in order to test* is the wrong way round — it makes the default branch the place
unverified work lands. But the local-marketplace route has a trap that costs more time than
the merge would, so the mechanics matter. **All of the following was measured on Claude Code
2.1.x, not inferred from the docs.**

**Never edit the installed copy under `~/.claude/plugins/cache/`.** It is a *copy*, not a
link to your checkout (verified: different inodes), and a hand-edit there is silently
discarded by the next update — measured, the marker written into the cache was simply gone
after `claude plugin update`, with no error and no warning. It is also the one path a
sandboxed session cannot write to. If you find yourself reaching for `sed` inside the cache,
the loop below is what you actually wanted.

**Step 1 — a marketplace directory is not your plugin checkout.** You need a *separate*
directory containing `.claude-plugin/marketplace.json`, whose entry points at the plugin by
relative path. Pointing `marketplace add` at a plugin repo does not work. Lay it out like
this, once:

```
~/dev-marketplace/
  .claude-plugin/marketplace.json     <- the catalog
  my-plugin/                          <- a symlink to your real checkout
```

```bash
mkdir -p ~/dev-marketplace/.claude-plugin
ln -s ~/ClaudeWorkspace/my-plugin ~/dev-marketplace/my-plugin
cat > ~/dev-marketplace/.claude-plugin/marketplace.json <<'JSON'
{
  "name": "dev",
  "owner": { "name": "you" },
  "plugins": [
    { "name": "my-plugin", "source": "./my-plugin",
      "description": "Local dev copy, loaded from a working checkout." }
  ]
}
JSON
```

The source must start with `./` and resolves against the marketplace root, not against
`.claude-plugin/`.

**Step 2 — add it and install:**

```bash
claude plugin marketplace add ~/dev-marketplace
claude plugin install my-plugin@dev
```

**Step 3 — know how to make an edit take effect.** This is the part that wastes time.
A relative-path source is **copied into the version-keyed cache**, so a source edit does
*not* appear in the installed copy on its own, and neither `marketplace update` nor
`plugin update` will bring it over: `plugin update` compares versions and reports *"already
at the latest version"* while leaving the stale copy in place. All three commands exit 0, so
nothing tells you the edit did not land.

Two ways forward, and it is worth choosing deliberately:

- **Bump the dev plugin's `version` for each round you need to see installed**, then
  `claude plugin marketplace update dev && claude plugin update my-plugin@dev`. Verified to
  propagate. Clunky, but it works unattended and from inside a Claude Code session.
- **Test the behaviour directly instead of through an install**, where the change is in a
  script or library the plugin ships — run it from the checkout. Usually the fastest loop,
  and for a hook or CLI it exercises the same code the installed copy would.

A `command` source with `mode: "link"` *does* load the directory in place without copying,
which would be the ideal dev loop — but **it cannot be accepted from inside a Claude Code
session**: the install refuses and tells you to run it from your own terminal, because a
marketplace-declared command needs a human to review it. Useful to know, not something an
agent can set up on its own.

**Step 4 — clean up**, so a dev marketplace does not linger and shadow the real one:

```bash
claude plugin uninstall my-plugin@dev
claude plugin marketplace remove dev
```

Then merge, and use `get-haiggoh apply` for the question only the published branch can
answer: does it work the way a consumer actually receives it, through the real fetch and
install path.

### Why entries are not pinned with `ref`

A marketplace plugin entry *can* carry `ref` (a branch or tag) or `sha`. The catalog here
deliberately does not use them for development. A pin lives in `marketplace.json`, which is
published and read by every consumer; it keeps resolving successfully long after the branch
stops being interesting, and removing it depends on someone remembering to. Pinning has one
good use — holding consumers at a known-good version after a bad release — which is a
deliberate, visible act with an obvious removal trigger. Reaching for it to avoid a merge
trades a one-line merge for silent, published, mutable state.

## Installation
This tool is typically installed as part of the get-haiggoh package. The scripts are located in the `bin/` directory:

- `bin/get-haiggoh.py` - Direct command-line interface
- `bin/get-haiggoh-menu` - Menu-driven interface

Both scripts are designed to be run from the repository root or via their absolute paths.