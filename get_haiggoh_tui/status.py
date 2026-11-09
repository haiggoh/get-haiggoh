"""get_haiggoh_tui.status — installed/latest status for plugins and tools (stdlib only).

Task 2 of docs/superpowers/plans/2026-11-08-tui-01-get-haiggoh-tui.md. Tests never touch
real ~/.claude, real brew or the network: paths come from env overrides and the run/fetch
callables are injectable.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

from .inventory import Row, brand_marks, load_catalog

REPO_ROOT = Path(__file__).resolve().parents[1]
SELF_NAME = "get-haiggoh"


def load_cli_module(repo_root: Path) -> ModuleType:
    """Import bin/get-haiggoh.py as a module (importlib on the file path)."""
    repo_root = Path(repo_root)
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    spec = importlib.util.spec_from_file_location(
        "get_haiggoh_cli", repo_root / "bin" / "get-haiggoh.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _core():
    import get_haiggoh_core as c
    return c


def _marks() -> dict[str, str]:
    return brand_marks((REPO_ROOT / "docs" / "branding.md").read_text(encoding="utf-8"))


def plugin_rows(cached: bool) -> list[Row]:
    """Rows for every marketplace plugin (self included, marketplace order).
    cached=True ⇒ remote_versions come from the day's refresh cache, no network at all."""
    c = _core()
    cli = load_cli_module(REPO_ROOT)
    remote_versions = c.load_cached_versions(c.refresh_stamp_path()) if cached else None
    _missing, _outdated, all_status = cli._compute(remote_versions=remote_versions)
    by_name = {s["name"]: s for s in all_status}
    plugins, _tools, extras = load_catalog(REPO_ROOT)
    marks = _marks()
    rows: list[Row] = []
    for p in plugins:
        name = p["name"]
        s = by_name.get(name, {})
        status = s.get("status") or "missing"
        if status == "unknown":
            status = "missing"
        rows.append(Row(
            name=name, section="plugin", mark=marks.get(name, ""),
            description=p.get("description", ""),
            adds=(extras.get(name) or {}).get("adds", ""),
            installed=s.get("installed_version"),
            latest=s.get("remote_version"),
            status=status,  # type: ignore[arg-type]
            diagnostic=s.get("diagnostic"),
            menu=(extras.get(name) or {}).get("menu"),
            tool=None))
    return rows


def tool_status(tool: dict, run=subprocess.run, fetch=None) -> tuple[str | None, str | None, dict | None]:
    """(installed, latest, diagnostic) for a related tool. Installed: `brew list --versions
    <short formula name>` when brew is present, else the tool's own version_cmd. Latest: the
    repo's latest GitHub release tag minus 'v'. A failed latest fetch sets `diagnostic` and
    returns latest=None — never raises."""
    c = _core()
    if fetch is None:
        fetch = c.fetch_url
    installed: str | None = None
    formula = tool.get("formula")
    if formula:
        short = str(formula).split("/")[-1]
        try:
            r = run(["brew", "list", "--versions", short], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                installed = r.stdout.strip().split()[-1]
        except (FileNotFoundError, OSError):
            pass  # brew absent -> fall through to version_cmd
    if installed is None:
        vc = tool.get("version_cmd")
        if vc:
            try:
                r = run(list(vc), capture_output=True, text=True)
                if r.returncode == 0 and r.stdout.strip():
                    installed = r.stdout.strip().split()[-1]
            except (FileNotFoundError, OSError):
                pass
    latest: str | None = None
    diagnostic: dict | None = None
    repo = tool.get("repo") or ""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        body = fetch(url, 10)
        tag = (json.loads(body) or {}).get("tag_name") or ""
        latest = tag[1:] if tag.startswith("v") else (tag or None)
    except Exception as exc:
        diagnostic = {
            "url": url,
            "problem": f"fetch failed: {exc}",
            "meaning": ("the latest release tag could not be checked; the row is UNVERIFIED, "
                        "never 'current'"),
            "fix": f"check connectivity, then: curl -fsSL {url}",
        }
    return installed, latest, diagnostic


def _tool_row(tool: dict, marks: dict[str, str]) -> Row:
    c = _core()
    installed, latest, diagnostic = tool_status(tool)
    if diagnostic:
        status = "unverified"
    elif installed is None:
        status = "missing"
    elif latest and c.remote_is_newer(installed, latest):
        status = "outdated"
    else:
        status = "current"
    return Row(
        name=tool["name"], section="tool", mark=marks.get(tool["name"], ""),
        description=tool.get("description", ""), adds=tool.get("adds", ""),
        installed=installed, latest=latest, status=status,  # type: ignore[arg-type]
        diagnostic=diagnostic, menu=tool.get("menu"), tool=tool)


def build_rows(cached: bool) -> list[Row]:
    """get-haiggoh first, then plugins in marketplace order, then related tools."""
    _plugins, tools, _extras = load_catalog(REPO_ROOT)
    marks = _marks()
    prows = plugin_rows(cached)
    self_row = next((r for r in prows if r.name == SELF_NAME), None)
    rows: list[Row] = ([self_row] if self_row else []) + [r for r in prows if r.name != SELF_NAME]
    rows += [_tool_row(t, marks) for t in tools]
    return rows
