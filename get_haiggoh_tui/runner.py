"""get_haiggoh_tui.runner — execute planned steps, verify by re-read state, resume self-update.

Task 5 of docs/superpowers/plans/2026-11-08-tui-01-get-haiggoh-tui.md. Tests never touch
real claude/brew/git or the network: `execute` and `reread` are injectable.
"""
from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .routes import Step
from .status import build_rows

REPO_ROOT = Path(__file__).resolve().parents[1]
PENDING_SCHEMA = 1


@dataclass
class StepResult:
    step: Step
    ok: bool
    output: str


def _core():
    import get_haiggoh_core as c
    return c


def _ok_from_state(step: Step, before, after) -> bool:
    """ok from the re-read row, never from the exit code: install ⇒ row now installed;
    update ⇒ installed version actually moved and is no longer behind the known latest;
    uninstall ⇒ row is gone/missing."""
    c = _core()
    if after is None:
        return False
    if step.op == "install":
        return after.installed is not None and after.status != "missing"
    if step.op == "uninstall":
        return after.installed is None or after.status == "missing"
    # update
    before_inst = before.installed if before else None
    if after.installed is None or after.installed == before_inst:
        return False
    if before is not None and before.latest and after.installed:
        if c.remote_is_newer(after.installed, before.latest):
            return False  # still behind the version we wanted
    return True


def _run_release_installer(step: Step, row, execute) -> tuple[str, bool]:
    """Download the fallback asset (glob matched against the latest release's assets)
    into a fresh tempdir and run it by path."""
    c = _core()
    tool = (row.tool or {}) if row else {}
    fallback = tool.get("fallback") or {}
    pattern = fallback.get("asset")
    repo = tool.get("repo")
    if not (pattern and repo):
        return ("no release-installer asset declared", False)
    api = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        rel = json.loads(c.fetch_url(api, 10))
        assets = [a.get("name", "") for a in rel.get("assets", [])]
        name = next((a for a in assets if fnmatch.fnmatch(a, pattern)), None)
        if not name:
            return (f"no asset matching {pattern!r} on the latest release", False)
        url = f"https://github.com/{repo}/releases/download/{rel.get('tag_name')}/{name}"
        body = c.fetch_url(url, 60)
    except Exception as exc:
        return (f"release-installer download failed: {exc}", False)
    d = tempfile.mkdtemp(prefix="get-haiggoh-installer-")
    asset = Path(d) / name
    asset.write_bytes(body)
    asset.chmod(0o755)
    r = execute(["/bin/bash", str(asset)], capture_output=True, text=True)
    return ((r.stdout or "") + (r.stderr or ""), True)


def _git_argv(step: Step, row) -> list[str]:
    repo = ((row.tool or {}).get("repo")) if row else None
    if not repo:
        return step.argv
    dest = Path.home() / ".local" / "share" / "get-haiggoh" / "clones" / step.name
    return ["git", "clone", f"https://github.com/{repo}.git", str(dest)]


def _touch_skip_list(step: Step, ok: bool) -> None:
    """Install removes the name from the skip list; uninstall adds it — so the
    SessionStart nudge respects the user's choice."""
    if not ok:
        return
    c = _core()
    path = c.skip_list_path()
    skip = c.load_skip_list(path)
    if step.op == "install":
        skip.pop(step.name, None)
    elif step.op == "uninstall":
        skip[step.name] = "both"
    else:
        return
    c.save_skip_list(path, skip)


def run_steps(steps, execute=subprocess.run, reread=build_rows, on_event=lambda e: None):
    """Run every step even after a failure. `ok` is decided by re-reading state after
    each step (installed version changed as expected / row gone after uninstall),
    never by the exit code alone."""
    try:
        rows = {r.name: r for r in reread(False)}
    except Exception:
        rows = {}
    results: list[StepResult] = []
    for step in steps:
        on_event(("start", step))
        if step.route == "release-installer":
            output, ran = _run_release_installer(step, rows.get(step.name), execute)
        elif step.route == "git":
            r = execute(_git_argv(step, rows.get(step.name)), capture_output=True, text=True)
            output, ran = (r.stdout or "") + (r.stderr or ""), True
        elif step.argv:
            r = execute(step.argv, capture_output=True, text=True)
            output, ran = (r.stdout or "") + (r.stderr or ""), True
        else:
            output, ran = step.note or "not run", False
        try:
            after_rows = {r.name: r for r in reread(False)}
        except Exception:
            after_rows = rows
        ok = _ok_from_state(step, rows.get(step.name), after_rows.get(step.name))
        _touch_skip_list(step, ok)
        result = StepResult(step, ok, output if ran else (step.note or output))
        results.append(result)
        on_event(("result", result))
        rows = after_rows
    return results


def _atomic_write_json(path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def write_pending(path, op, names) -> None:
    """Atomic {"schema": 1, "op", "names", "created"} — the queue the relaunched
    process resumes exactly once."""
    _atomic_write_json(path, {"schema": PENDING_SCHEMA, "op": op,
                              "names": list(names),
                              "created": datetime.now(timezone.utc).isoformat()})


def read_pending(path) -> dict | None:
    """The pending dict, or None when absent/corrupt/wrong schema."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) and data.get("schema") == PENDING_SCHEMA else None


def clear_pending(path) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def consume_pending(path) -> dict | None:
    """Read + clear exactly once (the --resume entry point uses this)."""
    data = read_pending(path)
    if data is not None:
        clear_pending(path)
    return data


def self_update_then_relaunch(steps, pending_path, execv=os.execv, execute=subprocess.run,
                              reread=build_rows) -> bool:
    """If the first step is get-haiggoh and more follow: run the self-update on the old
    code, write_pending for the rest, then execv bin/get-haiggoh-tui --resume so the NEW
    process finishes the bulk run — 'one keypress' stays true."""
    if not steps or steps[0].name != "get-haiggoh" or len(steps) < 2:
        return False
    first, rest = steps[0], steps[1:]
    run_steps([first], execute=execute, reread=reread)
    names: list[str] = []
    for s in rest:
        if s.name not in names:
            names.append(s.name)
    write_pending(pending_path, first.op, names)
    script = REPO_ROOT / "bin" / "get-haiggoh-tui"
    execv(str(script), [str(script), "--resume"])
    return True  # only reached when execv is faked
