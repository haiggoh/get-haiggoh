"""get_haiggoh_tui.brew_gate — the 🍺 Homebrew gate (stdlib only).

Task 4 of docs/superpowers/plans/2026-11-08-tui-01-get-haiggoh-tui.md. Homebrew is always
written `🍺 Homebrew` in UI copy; the notice copy is exact (Global Constraints).
"""
from __future__ import annotations

from .inventory import Row
from .routes import REPO_ROOT, Step, _row_formula_and_fallback, brew_path, load_catalog

INSTALL_ARGV = ["/bin/bash", "-c",
                "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"]
BUTTONS = ("Install 🍺 Homebrew", "Continue without 🍺 Homebrew")


def needs_brew(steps: list[Step]) -> list[str]:
    """Names whose step needs Homebrew (deduped, step order)."""
    seen: list[str] = []
    for s in steps:
        if s.needs_brew and s.name not in seen:
            seen.append(s.name)
    return seen


def _join_names(names: list[str]) -> str:
    if len(names) <= 1:
        return names[0] if names else ""
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + " and " + names[-1]


def notice_text(names: list[str]) -> str:
    """Exact notice copy (Global Constraints); names joined ', ' with ' and ' before the last."""
    return ("🍺 Homebrew will be installed now — it makes future updates of "
            f"{_join_names(list(names))} easier. It asks for your Mac password once.")


def decline_lines(rows: list[Row], names: list[str]) -> list[str]:
    """On opt-out, say plainly what continues via which route and what it loses:
    '{mark} {name}: continuing via {route}' + ' — {without_brew_loses}' when set."""
    _plugins, _tools, extras = load_catalog(REPO_ROOT)
    wanted = set(names)
    lines: list[str] = []
    for r in rows:
        if r.name not in wanted:
            continue
        formula, fallback, loses = _row_formula_and_fallback(r, extras)
        if r.section == "plugin" and not formula:
            route = "plugin"
        elif fallback:
            route = str(fallback.get("kind", "git"))
        elif formula and r.section == "plugin":
            route = "plugin"  # the plugin step still runs without brew
        else:
            route = "brew"
        line = f"{r.mark} {r.name}: continuing via {route}"
        if loses:
            line += f" — {loses}"
        lines.append(line)
    return lines


def verify_installed() -> bool:
    """brew_path() is not None, re-checked AFTER the installer ran — never assumed."""
    return brew_path() is not None
