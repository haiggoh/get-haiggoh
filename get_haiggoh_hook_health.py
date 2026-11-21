#!/usr/bin/env python3
"""Conservative recovery for stale manual Codex hook references.

Only a trusted native plugin hook with identical behavior can replace a missing
manual duplicate. Never executes the missing command or edits plugin state.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import signal
import stat
import subprocess
import tempfile
import time


def script_command(command, strict=True):
    """Accept simple interpreter/script calls only; never evaluate shell syntax."""
    try:
        parts = shlex.split(command)
    except (ValueError, TypeError):
        return None
    if len(parts) < 2 or Path(parts[0]).name not in ("python", "python3", "bash", "sh"):
        return None
    raw = parts[1]
    if raw.startswith("$HOME/"):
        raw = str(Path.home()) + raw[5:]
    if "$" in raw or chr(96) in raw or not ("/" in raw or raw.startswith("~")):
        return None
    # Matching literal shlex tokens is unsafe when the shell can expand or execute
    # them differently. Recognize such missing paths for diagnosis, never repair.
    if strict and any(any(c in p for c in ";&|<>$" + chr(96) + "\n\r*?[](){}")
                      for p in [parts[0], raw, *parts[2:]]):
        return None
    return parts[0], Path(raw).expanduser(), parts[2:]


def script_identity(path):
    """Recognized cache relocation or documented local-to-free queue-hook lineage."""
    parts = path.parts
    for i in range(len(parts) - 5):
        if parts[i:i + 2] == ("plugins", "cache") and parts[i + 2] == "haiggoh":
            plugin = parts[i + 3]
            return ("free-agents" if plugin == "local-agents" else plugin, tuple(parts[i + 5:]))
    if path.name == "local-queue-stop-hook.py" and ".claude" in parts and "scripts" in parts:
        return "free-agents", ("bin", path.name)
    return None


def equivalent(manual, candidate, event, matcher):
    if (candidate.get("source") != "plugin" or candidate.get("enabled") is not True
            or candidate.get("trustStatus") != "trusted" or candidate.get("async")
            or str(candidate.get("eventName", "")).lower() != event.lower()
            or candidate.get("matcher") != matcher):
        return False
    parsed = script_command(candidate.get("command"))
    if not parsed:
        return False
    interpreter, live, arguments = parsed
    identity = script_identity(manual[1])
    if not identity or candidate.get("pluginId") != identity[0] + "@haiggoh":
        return False
    root = Path(candidate.get("sourcePath") or "").parent.parent
    try:
        relative = tuple(live.relative_to(root).parts)
    except ValueError:
        return False
    return (interpreter == manual[0] and arguments == manual[2]
            and relative == identity[1] and live.is_file())


def atomic_write(path, expected, replacement):
    """Exact backup and optimistic concurrency check; preserve mode and symlinks."""
    if path.is_symlink():
        raise ValueError("hooks.json is a symlink; repair its authoritative file explicitly")
    mode = stat.S_IMODE(path.stat().st_mode)
    if path.read_bytes() != expected:
        raise ValueError("hooks.json changed concurrently; leaving it untouched")
    fd, backup = tempfile.mkstemp(prefix=path.name + ".bak-hook-repair-", dir=path.parent)
    with os.fdopen(fd, "wb") as out:
        out.write(expected)
        out.flush()
        os.fsync(out.fileno())
    fd, staging = tempfile.mkstemp(prefix=".hooks-repair-", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as out:
            out.write(replacement)
            out.flush()
            os.fsync(out.fileno())
        if path.read_bytes() != expected:
            raise ValueError("hooks.json changed concurrently; exact backup kept, no replacement")
        os.replace(staging, path)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)
    return backup


def unique_object(pairs):
    """Duplicate JSON keys are ambiguous configuration, never safe to rewrite."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("hooks.json contains duplicate object keys")
        result[key] = value
    return result


def claude_notice():
    """Diagnose literal manual script targets without executing or changing settings."""
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir is not None and (not config_dir or not Path(config_dir).is_absolute()):
        return "get-haiggoh: CLAUDE_CONFIG_DIR must be an absolute directory; hook health not checked."
    config = (Path(config_dir) if config_dir is not None else Path.home() / ".claude") / "settings.json"
    try:
        try:
            raw = config.read_bytes()
        except FileNotFoundError:
            return ""
        doc = json.loads(raw, object_pairs_hook=unique_object)
        if not isinstance(doc, dict):
            raise ValueError("settings must be an object")
        if doc.get("disableAllHooks") is True:
            return ""
        events = doc.get("hooks", {})
        if not isinstance(events, dict):
            raise ValueError("hooks must be an object")
        missing = []
        for event, groups in events.items():
            if not isinstance(groups, list):
                raise ValueError("hook groups must be arrays")
            for group in groups:
                if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                    raise ValueError("hook group must contain hooks")
                if group.get("enabled") is False:
                    continue
                for hook in group["hooks"]:
                    if not isinstance(hook, dict):
                        raise ValueError("hook must be an object")
                    if hook.get("type") != "command" or hook.get("enabled") is False:
                        continue
                    command = hook.get("command")
                    if not isinstance(command, str) or any(ch in command.replace("$HOME/", "") for ch in ";&|<>$`\n\r*?[](){}\\"):
                        continue
                    try:
                        parts = shlex.split(command)
                    except ValueError:
                        continue
                    if not parts:
                        continue
                    raw_parts = re.findall(r'''(?:[^\s'\"]+|'[^']*'|"[^"]*")+''', command)
                    if len(raw_parts) != len(parts):
                        continue
                    if Path(parts[0]).name in ("python", "python3", "bash", "sh"):
                        if len(parts) < 2:
                            continue
                        index = 1
                    else:
                        index = 0
                    target, raw_target = parts[index], raw_parts[index]
                    if raw_target.startswith("~/") and "$" not in target:
                        target = str(Path.home()) + target[1:]
                    elif (os.environ.get("HOME") and target.count("$") == 1 and
                          (re.fullmatch(r"\$HOME/[^'\"]+", raw_target) or
                           re.fullmatch(r'"\$HOME/[^"\']+"', raw_target))):
                        target = str(Path.home()) + target[5:]
                    elif "$" in target:
                        continue
                    path = Path(target)
                    if path.is_absolute() and not path.exists():
                        missing.append(f"{event}: {path}")
        if missing:
            return "get-haiggoh: missing manual Claude hook target(s): " + "; ".join(missing) + ". Check the owner or installation. Restoring the original program at the same path may allow a loaded command to run; settings changes may require a new session."
        return ""
    except (OSError, ValueError, TypeError, UnicodeError):
        return "get-haiggoh: could not read or parse Claude settings.json; manual hook health was not checked."


def repair_manual_hooks(path, metadata, apply=False):
    result = {"repaired": [], "repairable": [], "unresolved": [], "backup": None}
    try:
        path = Path(path)
        if not path.exists():
            return result
        raw = path.read_bytes()
        original = json.loads(raw, object_pairs_hook=unique_object)
        document = copy.deepcopy(original)
        events = document.get("hooks", {})
        if not isinstance(events, dict):
            raise ValueError("hooks must be an object")
        for event, groups in events.items():
            if not isinstance(groups, list):
                raise ValueError("hook groups must be arrays")
            for group in groups:
                hooks = group.get("hooks")
                if not isinstance(hooks, list):
                    raise ValueError("group hooks must be arrays")
                kept = []
                for hook in hooks:
                    if not isinstance(hook, dict):
                        raise ValueError("hook must be an object")
                    parsed = script_command(hook.get("command"), strict=False)
                    if (hook.get("type") != "command" or not parsed or parsed[1].is_file()
                            or hook.get("enabled") is False or group.get("enabled") is False
                            or hook.get("async")):
                        kept.append(hook)
                        continue
                    candidates = ({c["command"] for c in metadata
                                   if equivalent(parsed, c, event, group.get("matcher"))}
                                  if script_command(hook.get("command")) else set())
                    missing = str(parsed[1])
                    if len(candidates) == 1:
                        result["repairable"].append(missing)
                    else:
                        kept.append(hook)
                        result["unresolved"].append(missing + ": no unique trusted equivalent")
                group["hooks"] = kept
            events[event] = [g for g in groups if g["hooks"] or g in original["hooks"][event]]
        if apply and result["repairable"]:
            body = (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode()
            result["backup"] = atomic_write(path, raw, body)
            result["repaired"] = list(result["repairable"])
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        result["unresolved"].append(str(exc))
    return result


def native_hooks(cwd):
    """Zero-inference native inventory; eight-second deadline plus bounded cleanup."""
    deadline = time.monotonic() + 8
    child = subprocess.Popen(["codex", "app-server", "--stdio"], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             start_new_session=True, bufsize=0)
    selector = selectors.DefaultSelector()
    selector.register(child.stdout, selectors.EVENT_READ)
    buffer = b""
    def send(value):
        child.stdin.write((json.dumps(value) + "\n").encode())
    try:
        send({"id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "get_haiggoh_hook_health", "version": "1"},
            "capabilities": {"experimentalApi": True}}})
        while time.monotonic() < deadline:
            if not selector.select(min(.2, max(0, deadline - time.monotonic()))):
                continue
            data = os.read(child.stdout.fileno(), 65536)
            if not data:
                raise ValueError("native hook inventory exited without a result")
            buffer += data
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                message = json.loads(line)
                if message.get("id") == 1:
                    if "error" in message:
                        raise ValueError("native hook inventory initialization failed")
                    send({"method": "initialized"})
                    send({"id": 2, "method": "hooks/list", "params": {"cwds": [str(cwd)]}})
                if message.get("id") == 2:
                    if "error" in message:
                        raise ValueError("native hooks/list failed")
                    return [hook for row in message["result"]["data"] for hook in row["hooks"]]
        raise ValueError("native hooks/list exceeded the eight-second deadline")
    finally:
        selector.close()
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()



def codex_home():
    raw = os.environ.get("CODEX_HOME")
    if raw is not None and (not raw or not Path(raw).is_absolute() or not Path(raw).is_dir()):
        raise ValueError("CODEX_HOME must be an existing absolute directory")
    return Path(raw) if raw is not None else Path.home() / ".codex"


def is_codex_payload(payload):
    """Identify the harness by its native transcript location, not a leaking lane flag."""
    transcript = payload.get("transcript_path") or ""
    if not transcript:
        return False
    native = Path(transcript).resolve()
    if native.is_relative_to(Path.home() / ".claude" / "projects"):
        return False
    return native.is_relative_to(codex_home().resolve() / "sessions")


def codex_notice(payload):
    """No RPC when no manual script is missing; unverified errors remain visible."""
    root = codex_home()
    if not root.is_dir():
        return "get-haiggoh: CODEX_HOME is not a directory; hook recovery skipped"
    config = root / "hooks.json"
    first = repair_manual_hooks(config, [])
    if not first["unresolved"]:
        return ""
    try:
        result = repair_manual_hooks(config, native_hooks(Path(payload.get("cwd") or os.getcwd())), apply=True)
    except (OSError, ValueError) as exc:
        return "get-haiggoh: hook recovery could not verify native metadata: " + str(exc)
    notices = []
    if result["repaired"]:
        notices.append("get-haiggoh: removed %d missing manual hook duplicate(s) already supplied by trusted plugins; exact backup: %s. Start a new chat if old hooks were already loaded."
                       % (len(result["repaired"]), result["backup"]))
    if result["unresolved"]:
        notices.append("get-haiggoh: unresolved hook reference(s): " + "; ".join(result["unresolved"])
                       + ". Investigate once; do not repeatedly retry the same missing path.")
    return "\n".join(notices)


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog=
        "Environment: CODEX_HOME selects the Codex config directory; HOME supplies its default. No provider changes or inference requests.")
    parser.add_argument("--config", type=Path, help="Explicit existing manual hooks.json; default CODEX_HOME/hooks.json")
    parser.add_argument("--metadata", type=Path, help="Verified native hooks/list JSON receipt; otherwise query native inventory")
    parser.add_argument("--apply", action="store_true", help="Back up and remove verified missing duplicates; default is check-only")
    args = parser.parse_args()
    if args.config is not None and not args.config.is_file():
        parser.error("--config must name an existing file")
    args.config = args.config or codex_home() / "hooks.json"
    if args.metadata:
        receipt = json.loads(args.metadata.read_text())
        metadata = receipt if isinstance(receipt, list) else [h for row in receipt["data"] for h in row["hooks"]]
    else:
        preliminary = repair_manual_hooks(args.config, [])
        metadata = native_hooks(Path.cwd()) if preliminary["unresolved"] else []
    result = repair_manual_hooks(args.config, metadata, apply=args.apply)
    print(json.dumps(result))
    return 1 if result["unresolved"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
