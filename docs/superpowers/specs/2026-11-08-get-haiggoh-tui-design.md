# get-haiggoh TUI — design

Date: 2026-11-08 · Status: draft for review · Branch: `docs/tui-design`

## Intent — why this exists

A newcomer who has just installed get-haiggoh does not know what cost-tracker, waypoints or
free-agents are, nor that related tools (transcript-distiller, human-shell, …) exist. Today
`bin/get-haiggoh-menu` is a five-option `print()` menu that only plans/applies plugins by name.

The TUI makes the whole haiggoh fleet **discoverable, understandable and easy to keep current**:

1. **Find** every haiggoh plugin and related tool in one list, each explained in plain words.
2. **Install** — ideally most newcomers take all of it, but every item stays a free choice.
3. **Update** — keeping everything current is the frequent, long-term job and must be one keypress.
4. **Manage** — jump into each item's own menu, uninstall what is unwanted.

Success: a newcomer opens it once, understands what each item does, presses one key and ends up
with the full set installed; afterwards, updating is "open, press `u`".

## Goals

- One Textual TUI listing all catalog plugins, then (in a separate lower section) related tools.
- Per row: tick box · brand mark + name · installed version · status column.
- Bulk install / bulk update / bulk uninstall of ticked rows; Select all / Unselect all.
- A CSL-style info box at the bottom describing the highlighted item.
- Enter on an item that has its own interactive menu opens that menu, styled to match.
- The install route (plugin marketplace, Homebrew, release installer, git) is chosen automatically.

## Non-goals

- No SessionStart nudge pointing at the TUI (offered, deliberately not chosen).
- No per-item action menu for items without their own menu: their Enter shows the info box only.
- Not a general package manager: only haiggoh catalog items.

## Anti-goals — failure even if it technically works

- A newcomer installs something without being able to see what it is and what it adds (hooks run
  every session — that must be visible before install).
- 🍺 Homebrew installed silently, or setup dead-ending because Homebrew was declined.
- An update path that runs on get-haiggoh's own stale code ("update said done, nothing changed").
- Menu overlays that drift from the item's real menu after that item's next release.
- Previously skipped items re-pushed on every launch.

## Decided with the user (2026-11-08)

### The list

```
👨🏻‍💻 Get Haiggoh
   Install and keep every haiggoh plugin up to date
   3 updates available · 4 not installed

   Claude Code plugins                       Installed   Latest
 ❯ [x] 👨🏻‍💻 get-haiggoh                        0.9.4       ✓
   [x] 🧭 waypoints                          0.14.3      ✓
   [x] 💸 cost-tracker                       0.20.8      0.20.9
   [ ] 🛘🥾 watch-your-step                   0.8.1       ✓
   [x] …                                     —           not installed
   Related tools
   [x] … transcript-distiller                0.8.4       ✓
   [x] … human-shell                         1.4.0       1.4.1
   [x] … mac-claude-migration                —           not installed
   [x] … mac-iphone-backup-cloudsync         —           not installed

   Select all · Unselect all     [ Update 3 ]  [ Install 4 ]  [ Uninstall ]
╭─ 🧭 waypoints ─────────────────────────────── installed 0.14.3 ✓ ─╮
│ Persistent open-items reminder: a SessionStart banner listing      │
│ unfinished tasks until each is marked done.                        │
│ Adds: 1 skill · SessionStart hook · waypoints.py CLI               │
╰────────────────────────────────────────────────────────────────────╯
 space tick · enter open · a all · n none · u update · i install · x uninstall · q quit
```

The user approved this layout and the info box. Marks shown are illustrative: **the brand mark of
each item is its GitHub-About emoji, read from `docs/branding.md` "Marks" table** — never invented.

- **Status column:** green `✓` when installed == latest; the newer version number when outdated;
  `not installed` when absent. Installed column shows `—` when absent.
- **Sections:** "Claude Code plugins" (the 16 entries of `.claude-plugin/marketplace.json`), then
  "Related tools": transcript-distiller, human-shell, mac-claude-migration,
  mac-iphone-backup-cloudsync.
- **Self row:** get-haiggoh pinned first; always updated before anything else, then the TUI
  relaunches on the new version; excluded from bulk uninstall; single uninstall only behind an
  extra warning.
- **Summary line** under the title counts updates available and items not installed.

### Tick defaults (user accepted the proposal)

- **First launch** (no prior get-haiggoh state): every not-installed item starts ticked; "Unselect
  all" is right there.
- **Later launches:** only outdated items start ticked. Items the user left unticked/uninstalled
  stay unticked — never re-pushed. (Existing `skip_list` in `get_haiggoh_core.py` is the natural
  store for "deliberately skipped".)
- Separate buttons: **Update N** acts only on ticked installed-and-outdated rows; **Install N**
  only on ticked not-installed rows; counts follow the ticks live. Update never installs anything
  new.

### Uninstall

Per-item and **bulk** uninstall allowed. A confirm screen lists every item and what removing it
takes away (hooks, skills, CLIs, Dock icons). Uninstalled items remain listed as `not installed`.

### Info box

Same look and behaviour as CSL's `#info` box (`free-agents/bin/session_picker.py:801`, rounded
`ansi_bright_black` frame; follows both keyboard highlight and mouse hover, `session_picker.py:586`).
Contents: title line (mark + name, installed version + status), the item's about text, an
"Adds:" line (what installing changes), and — when relevant — the route it will use.

**About text source:** the approved catalog descriptions (`catalog-parity.py` keeps them in sync).
Related tools get catalog entries too, so there is one source of truth for README, marketplace and
TUI — no description copied into TUI code.

### Install routes — chosen automatically, never asked

Newcomers should not have to think about routes. Route table:

| Item | Preferred route | Fallback without Homebrew |
|---|---|---|
| 15 Claude Code plugins | plugin marketplace (`claude plugin …`) | — (no brew involved) |
| free-agents | plugin + 🍺 formula (Python 3.14, modern bash for `csl`) | plugin only; CLI via release installer if one exists |
| transcript-distiller | 🍺 `haiggoh/tap/claude-code-transcript-distiller` | release installer `.zsh` (needs a Python ≥ its minimum) |
| human-shell | 🍺 `haiggoh/tap/human-shell` (user: Dock icon via dockutil is core value) | release installer `.zsh` (no Dock icon; opens ~/Applications) |
| mac-claude-migration | 🍺 formula — **to be created, see Prerequisite** | git clone / release |
| mac-iphone-backup-cloudsync | 🍺 `haiggoh/tap/mac-iphone-backup-cloudsync` | builder to determine |

- If Homebrew is present: use the formula wherever one exists (`brew upgrade` = easy future updates).
- If Homebrew is absent: it is installed **only** when a ticked item benefits from it.

### The 🍺 Homebrew moment

Before installing Homebrew, the TUI pauses with an honest notice, always showing the 🍺 emoji
with the word Homebrew:

> 🍺 Homebrew will be installed now — it makes future updates of free-agents, human-shell and
> transcript-distiller easier. It asks for your Mac password once.
> [ Install 🍺 Homebrew ]  [ Continue without 🍺 Homebrew ]

On opt-out, say plainly which items continue via an alternative route and what they lose (e.g.
"human-shell: no Dock icon"), then proceed. Homebrew's installer needs an admin password in a real
terminal (users on managed Macs may need to elevate first); the TUI must hand the terminal to it
and report the real outcome afterwards (verify `brew` resolves), not assume success.

### Item menus

- Items **with** their own interactive menu — Enter opens it. Verified 2026-11-08:
  - free-agents → `csl` (already Textual)
  - waypoints → `waypoints_menu.py`
  - cost-tracker → bare `cost-tracker` / `cost-tracker menu`
  - lasting-plans → bare `lasting-plans` (dashboard + numbered menu)
  - check-code → `check-code.py setup`
  - mac-claude-migration → `./backup.sh` destination menu
  - transcript-distiller → `cc_transcript.py` interactive prompts
- Items **without** one — Enter shows/focuses the info box only.
- **CSL hand-off:** same terminal window. get-haiggoh steps aside (Textual `suspend`) and runs
  `csl --return-to get-haiggoh`; on exit, get-haiggoh reappears where the user left it.
- **Non-Textual menus get a Textual overlay** so they look native inside get-haiggoh (user's
  words: "a textual overlay that can seamlessly be integrated").
- **Fully native, including follow-up prompts** (user, after builder check): not only the action
  list but every follow-up question an action asks (e.g. backup.sh's destination prompts,
  check-code setup's language choices) is a Textual dialog in CSL style. Each repo therefore
  declares its prompts as data too — question, choices/free text, validation, default — and the
  action's argv is built from the answers. Non-interactive actions show their output in a Textual
  panel. The terminal is handed over only in the transition fallback below. This is a bigger
  change in each of the six repos and is accepted as such.
- **Every menu opened from get-haiggoh, CSL included, gets `👨🏻‍💻 Back to Get Haiggoh` as its
  LAST action item** — only when launched from get-haiggoh; launched on its own, it is absent
  (mirrors CSL's `🏠 Back to Home`, `session_picker_model.py:984`).

### Theme

Match CSL exactly: same ANSI palette, cyan `❯` cursor, rounded bright-black info box, italic
dim version footer. The two tools should feel like one family. Follow the house menu grammar
check-code enforces (`MENU-NAV`: numbers = actions, letters = navigation, `q` Quit, `b` Back).

### Launching

- `get-haiggoh` with no arguments on a TTY opens the TUI (replaces `get-haiggoh-menu` as the
  default; existing CLI flags/subcommands unchanged).
- From inside Claude Code: a `/get-haiggoh` command opens the TUI in its own Terminal.app window
  (a TUI cannot run inside the chat).

### Textual dependency

get-haiggoh is stdlib-only today. On first launch it creates a **private venv** (uv if present,
else `python3 -m venv`) holding Textual. If that fails for any reason, fall back to today's plain
numbered menu, so setup never dead-ends. Pin Textual to the version CSL uses (3.7.1 at time of
writing — read it from free-agents, do not trust this number).

### Prerequisite — mac-claude-migration 🍺 formula (part of this plan)

mac-claude-migration has no formula (verified: not on remote `haiggoh/homebrew-tap`, no branch of
the local tap ever touched one). Adding it is an early task of this plan: release tarball, SHA,
formula in `homebrew-tap`, shipped via that repo's normal release flow. Until it ships, the TUI
uses the git route.

## My calls (the designer's, not the user's — check these)

1. **Menus and prompts as data.** The overlay calls each item's existing commands; it does not
   re-type menu labels/logic. Each repo with a menu declares it once as data (actions: label →
   argv template; prompts: question, choices, validation, default), e.g. a `--menu-spec` JSON
   output. Its own numbered menu and get-haiggoh's overlay both render from that declaration. Rejected: hand-copied menus in get-haiggoh (drift on every
   release); embedding a live PTY terminal widget (breaks the CSL look). This means small changes
   in each of the 6 non-Textual repos.
2. **Return signal is a flag, not an env var:** `--return-to get-haiggoh`. Env vars leak into
   later unrelated sessions from the same shell.
3. **Self-update first, then relaunch** on the new code before any other action — and the
   relaunched process **resumes the pending bulk operation** (queue + ticks written to a state
   file before the relaunch, consumed once, deleted after), so "one keypress" stays true. A
   leftover state file from a crash is offered for resume, never silently replayed.
4. **Transition fallback:** if an installed item predates the menu/prompt declaration (or its
   spec fails to parse), get-haiggoh suspends and runs that item's legacy menu as-is in the same
   terminal, then returns. Nothing is blocked; it becomes native once the item updates. So the six
   repo changes are not release-blocking for the TUI itself.
5. Status/version data reuses `get_haiggoh_core.py` (`compute_missing`, `compute_outdated`,
   `remote_plugin_version`, daily refresh cache). The TUI paints instantly from cache and refreshes
   remote versions in the background.
6. Related tools' installed versions: `brew list --versions` for brew installs, otherwise the
   tool's own `--version` / `VERSION` file.

## Left to the builder

- Module layout, how the TUI is split from the core, test strategy (house rule: delivery-level
  tests — PTY/pilot for input, real subprocess for installers; a mutation must go RED).
- Exact keybindings beyond those shown; how long-running installs show progress.
- The menu-spec format details, provided it stays one declaration per repo.
- Version bumps and release of every repo touched, via each repo's `rtc-ship.sh`.
