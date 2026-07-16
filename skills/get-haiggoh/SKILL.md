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
