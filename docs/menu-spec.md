# menu-spec v1 — a repo declares its own interactive menu as data

Adopted 2026-11-09 by the get-haiggoh TUI work (spec:
`docs/superpowers/specs/2026-11-08-get-haiggoh-tui-design.md`, "My call 1" — menus and
prompts as data, one declaration per repo, so get-haiggoh's overlay and the repo's own
menu both render from it and never drift).

A tool or plugin that has an interactive menu answers `--menu-spec` with a JSON document
on stdout and exits 0:

```json
{
  "menu_spec": 1,
  "title": "💸 cost-tracker",
  "actions": [
    {
      "label": "Set daily cap",
      "argv": ["cost-tracker", "cap", "{amount}"],
      "output": "panel",
      "prompts": [
        {
          "id": "amount",
          "question": "Daily cap in USD?",
          "type": "choice",
          "choices": [{"value": "20", "label": "$20"}, {"value": "40", "label": "$40"}],
          "default": "40",
          "pattern": null
        }
      ]
    }
  ]
}
```

## Fields

- `menu_spec` — must be `1`. Unknown versions are rejected by the consumer.
- `title` — non-empty string; rendered as the menu header.
- `actions` — list of actions:
  - `label` — non-empty string, the menu line.
  - `argv` — list of strings, the command to run. `{placeholder}` tokens (whole tokens
    only) are substituted from the prompt answers; the argv is NEVER shell-joined, so an
    answer containing `;` or spaces stays one argument.
  - `output` — `"panel"` (output shown in an overlay panel) or `"terminal"` (the escape
    hatch: the consumer suspends itself and the action owns the real TTY).
  - `prompts` — follow-up questions asked before running, as data:
    - `id` — referenced by a `{id}` placeholder in `argv`.
    - `question` — what is asked.
    - `type` — `"choice"` | `"text"` | `"confirm"`.
    - `choices` — required for `"choice"`: list of `{"value": …, "label": …}`.
    - `default` — default answer or null.
    - `pattern` — optional regex the text answer must match, or null.

## Validation rules (consumer side, `get_haiggoh_tui.menuspec.validate`)

- `menu_spec` must be the version the consumer understands.
- Every `{placeholder}` in an action's argv must have a prompt with that id; every
  prompt must be referenced by some placeholder.
- `"choice"` prompts must carry a `choices` list.
- `output` must be `"panel"` or `"terminal"`.

## Versioning and the legacy fallback

The catalog entry for an item declares, per menu:

- `spec_min_version` — the first installed version that answers `--menu-spec` correctly.
  get-haiggoh NEVER probes below it (a legacy script may read an unknown flag as a
  destination and write). Null = never probe.
- `return_to_min_version` — the first installed version that accepts
  `--return-to get-haiggoh` (a flag, never an env var). Below it, the legacy menu runs
  as-is via suspend and get-haiggoh reappears on exit.

Menus opened from get-haiggoh get `👨🏻‍💻 Back to Get Haiggoh` appended as the LAST action
(only when launched from get-haiggoh; launched on its own, it is absent).
