---
name: get-haiggoh
description: Use when the user asks to install all their haiggoh plugins, sync/update haiggoh plugins, or references "get-haiggoh" by name. Triggers on specific phrasing like "install all my haiggoh plugins", "get-haiggoh", "sync my haiggoh plugins", "install my other plugins" (haiggoh context established). Do NOT trigger on a bare generic "install everything" with no haiggoh context -- that's too easily confused with unrelated software installs.
---

# get-haiggoh

Installs/updates every published `haiggoh` Claude Code plugin from one place.

## Procedure

1. Run `python3 "$CLAUDE_PLUGIN_ROOT/bin/get-haiggoh.py" plan` (or the bare `get-haiggoh.py plan`
   if it's on the Bash-tool PATH via `bin/` injection).
2. Show the user the plan output verbatim.
3. If it says "Nothing to do", stop there -- no further action needed.
4. Otherwise, **ask for explicit confirmation** before proceeding -- installing/updating
   plugins is a visible, effectful action. Do not run `apply` without it.
5. On confirmation, run `get-haiggoh.py apply` and report the per-plugin install/update
   results verbatim (including any failures) back to the user.
6. If the user says to skip a specific plugin instead of installing/updating it, record
   that in `~/.claude/.get-haiggoh-skip.json` (a flat JSON object: `{"<plugin-name>":
   "install"|"update"|"both"}`) so the SessionStart nudge and future `plan` runs stop
   surfacing that specific plugin for that specific reason, while still catching
   genuinely new plugins later.

## What this can and cannot pull

- **Every plugin resolves from its repository's DEFAULT branch**, and outdated-detection
  reads the `version` in `.claude-plugin/plugin.json` at that branch's HEAD. There is no
  way to install from a feature branch, by design: this is a distribution tool, so what it
  fetches is what a consumer gets.
- **So if a change is pushed but not merged, `plan` will correctly say "Nothing to do".**
  When the user expects an update and the plan is empty, check whether the work was merged
  before suspecting the scan — that is the far more common cause. Do not report this as a
  bug in the scan, and do not work around it by pinning a `ref` in the catalog.
- **Merging is part of shipping a plugin here**, not a cleanup step afterwards. A plugin
  change is obtainable only once it is on the default branch and its version is bumped.
- **A same-version push is not reported either** — the install path is keyed on the version,
  so such an update has nowhere to land and the nag could never be satisfied.

## Dogfooding a plugin change before it is merged

Do not merge in order to test. But do not reach for the plugin cache either — the two
failure modes here are specific and both waste a lot of time, so follow this rather than
improvising.

**NEVER edit `~/.claude/plugins/cache/<owner>/<plugin>/<version>/` to test a change.** That
directory is a COPY of the source, not a link to it (measured: different inodes), and a
hand-edit is silently thrown away by the next `plugin update` — verified, the edit was gone
with no error. It is also unwritable from a sandboxed session, where the failure looks like a
filesystem permission fault and invites more workarounds. Editing the cache is never the
answer; it is the symptom of not knowing the loop below.

**The local-marketplace loop.** A marketplace is a directory holding
`.claude-plugin/marketplace.json` — it is NOT the plugin checkout, and `marketplace add`
pointed at a plugin repo does not work. Create one beside the checkout (symlink the plugin
in, entry source `"./my-plugin"`, which must start with `./`), then
`claude plugin marketplace add <that dir>` and `claude plugin install my-plugin@dev`.

**Then the part that surprises everyone: a source edit does not reach the installed copy by
itself.** A relative-path source is copied into the version-keyed cache. `marketplace update`
does not refresh it, and `plugin update` compares VERSIONS — it prints "already at the latest
version" and leaves the stale copy in place. Every command exits 0, so nothing reports that
the edit did not land. To see an edit installed, **bump the dev plugin's `version`**, then
`marketplace update` + `plugin update` (verified to propagate). Where the change lives in a
script or library the plugin ships, running it straight from the checkout is usually the
faster loop and exercises the same code.

A `command` source with `mode: "link"` loads the directory in place with no copy, which would
be the ideal loop, but it **cannot be accepted from inside a Claude Code session** — the
install refuses and requires a human in a real terminal. Do not plan an agent workflow around
it.

Clean up afterwards (`plugin uninstall my-plugin@dev`, `marketplace remove dev`) so a dev
marketplace does not linger next to the real one. Then merge, and run `apply` to answer the
separate question *does it work the way a consumer receives it*, through the real fetch and
install path — that catches packaging failures the pre-merge loop cannot see.

## Notes

- This skill/plugin excludes itself (`get-haiggoh`) from its own install/update list --
  installing itself is meaningless.
- A brand-new user still has to manually run `claude plugin marketplace add
  haiggoh/get-haiggoh` and `claude plugin install get-haiggoh@haiggoh` once, by hand --
  this plugin cannot bootstrap its own first install. Everything after that first
  install is automated.
- **Future extension (not built yet):** a curated/categorized install mode (e.g.
  "session-continuity" vs "automation-safety" groups) instead of install-everything,
  once the plugin list grows large enough that "everything" stops being the obvious
  default.
