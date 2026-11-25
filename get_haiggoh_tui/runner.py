"""get_haiggoh_tui.runner — execute planned steps, verify by re-read state, resume self-update.

Task 5 of docs/superpowers/plans/2026-11-08-tui-01-get-haiggoh-tui.md. Tests never touch
real claude/brew/git or the network: `execute` and `reread` are injectable.
"""
from __future__ import annotations

import fnmatch
import json
import math
import os
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .inventory import Row
from .routes import Step
from .status import build_rows

REPO_ROOT = Path(__file__).resolve().parents[1]
PENDING_SCHEMA = 1
DEFAULT_STEP_TIMEOUT = 600.0


@dataclass
class ExecResult:
    returncode: int | None
    output: str
    timed_out: bool = False
    cancelled: bool = False


@dataclass
class StepResult:
    step: Step
    ok: bool
    output: str
    outcome: str = ""
    after_row: Row | None = None

    def __post_init__(self):
        if not self.outcome:
            self.outcome = "ok" if self.ok else "failed"

    @property
    def after_version(self) -> str | None:
        return self.after_row.installed if self.after_row is not None else None


class RunControl:
    """Thread-safe stop handle shared between the UI thread and the run worker.
    request_stop may upgrade after_current -> immediate, never downgrades."""

    def __init__(self):
        self._lock = threading.Lock()
        self._stop: str | None = None
        self._proc = None

    @property
    def stop(self) -> str | None:
        with self._lock:
            return self._stop

    def request_stop(self, mode: str) -> None:
        with self._lock:
            if self._stop != "immediate":
                self._stop = mode
        if mode == "immediate":
            self.kill_current()

    def attach(self, proc) -> None:
        with self._lock:
            self._proc = proc
            stop = self._stop
        if stop == "immediate":
            self.kill_current()  # a stop that landed before attach still kills

    def detach(self) -> None:
        with self._lock:
            self._proc = None

    def kill_current(self) -> None:
        with self._lock:
            proc = self._proc
        if proc is None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass


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


def _prepare_release_installer(step: Step, row) -> tuple[str, Path | None]:
    """Download the fallback asset (glob matched against the latest release's assets)
    into a fresh tempdir. (error_output, asset_path) — asset_path None on failure."""
    c = _core()
    tool = (row.tool or {}) if row else {}
    fallback = tool.get("fallback") or {}
    pattern = fallback.get("asset")
    repo = tool.get("repo")
    if not (pattern and repo):
        return ("no release-installer asset declared", None)
    api = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        rel = json.loads(c.fetch_url(api, 10))
        assets = [a.get("name", "") for a in rel.get("assets", [])]
        name = next((a for a in assets if fnmatch.fnmatch(a, pattern)), None)
        if not name:
            return (f"no asset matching {pattern!r} on the latest release", None)
        url = f"https://github.com/{repo}/releases/download/{rel.get('tag_name')}/{name}"
        body = c.fetch_url(url, 60)
    except Exception as exc:
        return (f"release-installer download failed: {exc}", None)
    d = tempfile.mkdtemp(prefix="get-haiggoh-installer-")
    asset = Path(d) / name
    asset.write_bytes(body)
    asset.chmod(0o755)
    return ("", asset)


def _run_release_installer(step: Step, row, execute) -> tuple[str, bool]:
    """Legacy path: download the fallback asset and run it by path with `execute`."""
    err, asset = _prepare_release_installer(step, row)
    if asset is None:
        return (err, False)
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


def _killpg(proc, sig) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), sig)
    except ProcessLookupError:
        pass


def stream_execute(argv, *, on_line, control=None, timeout=None, kill_grace=2.0):
    """Run argv with stdout+stderr streamed through on_line, split on \\n and \\r,
    each piece decoded errors="replace"; a trailing piece without a newline is
    still delivered. `timeout` is an IDLE limit: `timeout` seconds with no output
    kills the whole process group (SIGTERM, then SIGKILL after kill_grace) and
    returns timed_out=True. control.attach/detach bracket the run; when
    control.stop == "immediate" and the process died by a signal, the result is
    cancelled=True. Popen failures are results, never raised."""
    try:
        proc = subprocess.Popen(list(argv), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True)
    except FileNotFoundError:
        return ExecResult(None, f"{argv[0]}: command not found")
    except PermissionError as exc:
        return ExecResult(None, str(exc))
    lock = threading.Lock()
    last_output = time.monotonic()
    raw: list[bytes] = []

    def _reader():
        nonlocal last_output
        out = proc.stdout
        assert out is not None  # stdout=PIPE above
        fd = out.fileno()
        pending = b""
        while True:
            try:
                block = os.read(fd, 4096)
            except (OSError, ValueError):
                break
            if not block:
                break
            with lock:
                last_output = time.monotonic()
            raw.append(block)
            pending += block
            while pending:
                cuts = [i for i in (pending.find(b"\n"), pending.find(b"\r")) if i != -1]
                if not cuts:
                    break
                i = min(cuts)
                piece, pending = pending[:i], pending[i + 1:]
                text = piece.decode("utf-8", errors="replace")
                if text:
                    on_line(text)
        if pending:
            text = pending.decode("utf-8", errors="replace")
            if text:
                on_line(text)

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()
    if control is not None:
        control.attach(proc)
    timed_out = False
    try:
        while True:
            try:
                proc.wait(0.05)
                break
            except subprocess.TimeoutExpired:
                pass
            if timeout is not None and timeout > 0:
                with lock:
                    idle = time.monotonic() - last_output
                if idle >= timeout:
                    timed_out = True
                    _killpg(proc, signal.SIGTERM)
                    try:
                        proc.wait(kill_grace)
                    except subprocess.TimeoutExpired:
                        _killpg(proc, signal.SIGKILL)
                        proc.wait()
                    break
    finally:
        if control is not None:
            control.detach()
    reader.join(timeout=1.0)
    output = b"".join(raw).decode("utf-8", errors="replace")
    cancelled = (control is not None and control.stop == "immediate"
                 and proc.returncode is not None and proc.returncode < 0)
    return ExecResult(proc.returncode, output, timed_out=timed_out, cancelled=cancelled)


def step_timeout_from_env(env: Mapping[str, str] = os.environ) -> float | None:
    """GET_HAIGGOH_STEP_TIMEOUT = seconds WITHOUT OUTPUT before a step is stopped
    (idle limit; the clock resets on every output line). Unset/empty ⇒
    DEFAULT_STEP_TIMEOUT (600); <= 0 ⇒ None (disabled); a set-but-invalid value
    raises ValueError naming the variable and the raw value — never silently
    falls back to the default."""
    raw = env.get("GET_HAIGGOH_STEP_TIMEOUT")
    if raw is None or raw == "":
        return DEFAULT_STEP_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(
            f"GET_HAIGGOH_STEP_TIMEOUT={raw!r} is not a number") from None
    if not math.isfinite(value):
        raise ValueError(
            f"GET_HAIGGOH_STEP_TIMEOUT={raw!r} is not a finite number") from None
    if value <= 0:
        return None
    return value


def run_steps(steps, execute=None, reread=build_rows, on_event=lambda e: None,
              control=None, timeout=None, stream=None, rows=None, reread_one=None):
    """Run every step even after a failure. `ok` is decided by re-reading state after
    each step (installed version changed as expected / row gone after uninstall),
    never by the exit code alone.

    execute given ⇒ the legacy blocking path, byte-for-byte. execute=None ⇒ every
    argv goes through `stream` (default stream_execute) with per-line ("output", …)
    events. reread_one given ⇒ local mode: `rows` (required) are the before-rows and
    only the current step's row is re-read after each step — `reread` is never called,
    so a run makes no network calls. Otherwise the full reread(False) sweep runs
    before and after each step, as before.
    """
    if reread_one is not None:
        if rows is None:
            raise ValueError("run_steps: rows= is required when reread_one is given")
        rows_map = {r.name: r for r in rows}
    else:
        try:
            rows_map = {r.name: r for r in reread(False)}
        except Exception:
            rows_map = {}
    stream_fn = stream if stream is not None else stream_execute
    results: list[StepResult] = []
    prev_name: str | None = None
    for step in steps:
        mode = control.stop if control is not None else None
        if mode == "immediate" or (mode == "after_current" and prev_name is not None
                                    and step.name != prev_name):
            result = StepResult(step, False, "", outcome="skipped")
            results.append(result)
            on_event(("result", result))
            continue
        on_event(("start", step))
        prev_name = step.name
        before_row = rows_map.get(step.name)
        res: ExecResult | None = None
        output, ran = "", False
        if execute is not None:
            if step.route == "release-installer":
                output, ran = _run_release_installer(step, before_row, execute)
            elif step.route == "git":
                r = execute(_git_argv(step, before_row), capture_output=True, text=True)
                output, ran = (r.stdout or "") + (r.stderr or ""), True
            elif step.argv:
                r = execute(step.argv, capture_output=True, text=True)
                output, ran = (r.stdout or "") + (r.stderr or ""), True
            else:
                output, ran = step.note or "not run", False
        else:
            def on_line(line, _step=step):
                on_event(("output", _step, line))

            if step.route == "release-installer":
                err, asset = _prepare_release_installer(step, before_row)
                if asset is None:
                    output, ran = err, False
                else:
                    res = stream_fn(["/bin/bash", str(asset)], on_line=on_line,
                                    control=control, timeout=timeout)
            elif step.route == "git":
                res = stream_fn(_git_argv(step, before_row), on_line=on_line,
                                control=control, timeout=timeout)
            elif step.argv:
                res = stream_fn(list(step.argv), on_line=on_line, control=control,
                                timeout=timeout)
            else:
                output, ran = step.note or "not run", False
            if res is not None:
                output, ran = res.output, True
        if reread_one is not None:
            try:
                after = reread_one(before_row)
            except Exception:
                after = before_row
            rows_map[step.name] = after
            after_row = after
        else:
            try:
                after_rows = {r.name: r for r in reread(False)}
            except Exception:
                after_rows = rows_map
            rows_map = after_rows
            after_row = after_rows.get(step.name)
        if res is not None and res.timed_out:
            ok, outcome = False, "timed_out"
        elif res is not None and res.cancelled:
            ok, outcome = False, "cancelled"
        else:
            ok, outcome = _ok_from_state(step, before_row, after_row), ""
        _touch_skip_list(step, ok)
        result = StepResult(step, ok, output if ran else (step.note or output),
                            outcome=outcome, after_row=after_row)
        results.append(result)
        on_event(("result", result))
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


def relaunch_with_pending(op, rest_steps, pending_path, execv) -> None:
    """Dedupe names → write_pending → execv bin/get-haiggoh-tui --resume, so the NEW
    process finishes the rest of the bulk run."""
    names: list[str] = []
    for s in rest_steps:
        if s.name not in names:
            names.append(s.name)
    write_pending(pending_path, op, names)
    script = REPO_ROOT / "bin" / "get-haiggoh-tui"
    execv(str(script), [str(script), "--resume"])


def self_update_then_relaunch(steps, pending_path, execv=os.execv, execute=subprocess.run,
                              reread=build_rows) -> bool:
    """If the first step is get-haiggoh and more follow: run the self-update on the old
    code, write_pending for the rest, then execv bin/get-haiggoh-tui --resume so the NEW
    process finishes the bulk run — 'one keypress' stays true."""
    if not steps or steps[0].name != "get-haiggoh" or len(steps) < 2:
        return False
    first, rest = steps[0], steps[1:]
    run_steps([first], execute=execute, reread=reread)
    relaunch_with_pending(first.op, rest, pending_path, execv)
    return True  # only reached when execv is faked
