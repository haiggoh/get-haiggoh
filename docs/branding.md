# haiggoh plugin branding — the credit-moment rule

Every haiggoh plugin shows its GitHub-About emoji at its **credit moments** — the moments
it demonstrably acted for the user — so you can see at a glance which plugin just played
a role. The mark is the About emoji **verbatim**; a pair is fine when the combination adds
meaning (🛘🥾, 📡🦾 = the two free-agents lanes).

## Credit moments only

Brand when the plugin just: found an issue, blocked a trap, warned about the budget,
offered session recovery, announced an update, or was invoked via a `/`-command (the
reply right after the skill loads). **Never** on idle surfaces: per-prompt hook chatter,
always-on statuslines, all-clear reports. Tone rule: a whimsical mark never appears at
the user's bad-news moments (e.g. the budget-exhausted ⚠️ stays plain).

## The three carriers

- **(A) Emit lines** in the plugin's own hooks/CLI (findings, blocks, warnings, notices).
- **(B)** A ≤3-line `## Branding (<mark>)` section in each SKILL.md, instructing the model
  to lead its first substantive reply after invocation with `<mark> <plugin>:`. Loads
  exactly at invocation — zero idle context cost.
- **(C)** Static surfaces: plugin.json `description`, marketplace.json, README h1,
  CLI `--help`/banner.

## Marks (GitHub About, verbatim)

waypoints 🧭 · free-agents 📡🦾 (lane-conditional: 📡 remote, 🦾 local) · check-code 🩻🔬 ·
watch-your-step 🛘🥾 · summon-skills 💡 · cost-tracker 💸 (never the statusline, never the
cap warning) · audit-loose-ends ✍️ · run-to-completion 🏃 (rtc-ship 🚢 at ship moments only) ·
measure-twice ⚖️ · no-hidden-changes 👁️ · brief-agents 📝 · resume-interrupted ⚡️ ·
get-haiggoh 👨🏻‍💻 · lasting-plans 📜 · mcp-smoke-test 🔌 ·
Claude-Code-Transcript-Distiller ⚗️ · codex-cost-tracker 💸 · echoprism 📐 ·
homebrew-tap 🚰 · mac-iphone-backup-cloudsync 📱 · mac-claude-migration 📦

## Never brand

Machine-parsed tokens (`# wys:allow`, flags, paths, JSON keys) · test assertion strings
(update them instead) · Textual markup-processed strings (use `Text` objects) ·
per-prompt suggestion listings · all-clear reports. Emoji width: an emoji renders 2
columns; ZWJ sequences render one glyph but count many code points — in wrapped/boxed
banners use the width-correction helper (see waypoints' core), and verify by eyeball, not grep.
