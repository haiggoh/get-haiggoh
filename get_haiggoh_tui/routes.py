"""get_haiggoh_tui.routes — install/update/uninstall routes as planned Steps (stdlib only).

Task 3 of docs/superpowers/plans/2026-11-08-tui-01-get-haiggoh-tui.md.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .inventory import Row, load_catalog

REPO_ROOT = Path(__file__).resolve().parents[1]
SELF_NAME = "get-haiggoh"

_BREW_VERBS = {"install": "install", "update": "upgrade", "uninstall": "uninstall"}


@dataclass
class Step:
    name: str
    op: Literal["install", "update", "uninstall"]
    route: Literal["plugin", "brew", "release-installer", "git"]
    argv: list[str]
    needs_brew: bool
    note: str | None


def brew_path() -> str | None:
    """shutil.which('brew') first, then the two standard macOS prefixes."""
    p = shutil.which("brew")
    if p:
        return p
    for candidate in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew"):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _plugin_argv(name: str, op: str) -> list[str]:
    return ["claude", "plugin", op, f"{name}@haiggoh"]


def _brew_argv(formula: str, op: str) -> list[str]:
    return ["brew", _BREW_VERBS[op], formula]


def _row_formula_and_fallback(row: Row, extras: dict) -> tuple[str | None, dict | None, str | None]:
    """(formula, fallback, without_brew_loses) for a row — tools from row.tool, plugins
    from catalog/plugin-extras.json."""
    if row.section == "tool" and row.tool:
        return (row.tool.get("formula"), row.tool.get("fallback"),
                row.tool.get("without_brew_loses"))
    ex = extras.get(row.name) or {}
    return ex.get("formula"), None, None


def plan_steps(rows: list[Row], ticks: set[str], op: Literal["install", "update", "uninstall"],
               brew_present: bool, brew_allowed: bool) -> list[Step]:
    """Plan the steps for the ticked rows under `op`.

    update ⇒ only ticked outdated rows (never installs anything new); install ⇒ only
    ticked missing rows; uninstall ⇒ ticked installed rows, minus get-haiggoh (bulk
    never removes the manager itself). get-haiggoh's step, when present, is first.
    A row with a formula takes the brew route iff brew_present or brew_allowed
    (needs_brew = not brew_present); otherwise its fallback; a null fallback yields a
    shown-not-run step (argv=[]) noted 'needs 🍺 Homebrew'. free-agents yields a plugin
    step plus, when brew is usable, a brew step."""
    _plugins, _tools, extras = load_catalog(REPO_ROOT)
    steps: list[Step] = []
    for row in rows:
        if row.name not in ticks:
            continue
        if op == "update" and row.status != "outdated":
            continue
        if op == "install" and row.status != "missing":
            continue
        if op == "uninstall":
            if row.status not in ("current", "outdated", "unverified"):
                continue
            if row.name == SELF_NAME:
                continue
        formula, fallback, without_brew_loses = _row_formula_and_fallback(row, extras)

        if row.section == "plugin":
            steps.append(Step(row.name, op, "plugin", _plugin_argv(row.name, op),
                              False, None))
            if formula and (brew_present or brew_allowed):
                steps.append(Step(row.name, op, "brew", _brew_argv(formula, op),
                                  not brew_present, None))
            continue

        # related tool
        if formula and (brew_present or brew_allowed):
            steps.append(Step(row.name, op, "brew", _brew_argv(formula, op),
                              not brew_present, None))
        elif fallback:
            kind = fallback.get("kind")
            route = kind if kind in ("release-installer", "git") else "git"
            argv = list(fallback.get("uninstall_argv") or []) if op == "uninstall" else []
            steps.append(Step(row.name, op, route, argv, not brew_present,
                              without_brew_loses))
        else:
            steps.append(Step(row.name, op, "brew", [], not brew_present,
                              "needs 🍺 Homebrew"))

    # get-haiggoh's step first, so a self-update runs before anything else
    steps.sort(key=lambda s: s.name != SELF_NAME)
    return steps
