"""get_haiggoh_tui.selection — first-run state and default ticks (stdlib only).

Task 3 of docs/superpowers/plans/2026-11-08-tui-01-get-haiggoh-tui.md.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .inventory import Row

STATE_SCHEMA = 1


def is_first_run(state_path: Path) -> bool:
    """True when no prior TUI state exists (missing/corrupt file counts as first run)."""
    try:
        data = json.loads(Path(state_path).read_text(encoding="utf-8"))
    except Exception:
        return True
    return not (isinstance(data, dict) and data.get("first_run_done") is True)


def mark_first_run_done(state_path: Path) -> None:
    """Atomic write of {"schema": 1, "first_run_done": true} (tmp file + os.replace)."""
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(state_path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"schema": STATE_SCHEMA, "first_run_done": True}, f)
            f.write("\n")
        os.replace(tmp, state_path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def default_ticks(rows: list[Row], first_run: bool) -> set[str]:
    """First launch: every missing + every outdated row starts ticked (Unselect all is
    right there). Later launches: outdated only — items the user left unticked or
    uninstalled are never re-pushed."""
    if first_run:
        return {r.name for r in rows if r.status in ("missing", "outdated")}
    return {r.name for r in rows if r.status == "outdated"}
