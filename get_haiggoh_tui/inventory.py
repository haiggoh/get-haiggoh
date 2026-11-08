"""get_haiggoh_tui.inventory — catalog loading and brand marks (stdlib only).

Task 1 of docs/superpowers/plans/2026-11-08-tui-01-get-haiggoh-tui.md.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass
class Row:
    name: str
    section: Literal["plugin", "tool"]
    mark: str
    description: str
    adds: str
    installed: str | None
    latest: str | None
    status: Literal["current", "outdated", "missing", "unverified"]
    diagnostic: dict | None
    menu: dict | None
    tool: dict | None


def brand_marks(branding_md: str) -> dict[str, str]:
    """Parse the '## Marks' section of docs/branding.md into {lowercase-name: mark}.

    Line shape: 'name MARK (optional note) · name2 MARK2 ...' — the mark is the
    second whitespace-separated token; parenthetical notes (which may themselves
    contain emoji) are ignored. Keys are lowercased so 'Claude-Code-Transcript-Distiller'
    resolves the tool name 'claude-code-transcript-distiller'.
    """
    marks: dict[str, str] = {}
    in_marks = False
    for line in branding_md.splitlines():
        if line.startswith("## "):
            in_marks = line[3:].strip().lower().startswith("marks")
            continue
        if not in_marks or not line.strip():
            continue
        for token in line.split("·"):
            parts = token.split()
            if len(parts) >= 2:
                marks[parts[0].lower()] = parts[1]
    return marks


def load_catalog(repo_root: Path) -> tuple[list[dict], list[dict], dict]:
    """Load (marketplace plugins, related tools, plugin extras) from the repo.

    plugins: .claude-plugin/marketplace.json['plugins']
    tools:   catalog/related-tools.json (list, spec order)
    extras:  catalog/plugin-extras.json (dict keyed by plugin name)
    """
    root = Path(repo_root)
    plugins = json.loads(
        (root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))["plugins"]
    tools = json.loads(
        (root / "catalog" / "related-tools.json").read_text(encoding="utf-8"))
    extras = json.loads(
        (root / "catalog" / "plugin-extras.json").read_text(encoding="utf-8"))
    return plugins, tools, extras
