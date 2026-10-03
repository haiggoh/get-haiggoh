"""PATH shims for haiggoh plugin CLIs.

Design: docs/superpowers/specs/2026-10-03-path-shortcuts-design.md. A plugin declares the
commands it wants on the user's shell PATH in a plain-text `shortcuts` file at its root (one
bare command name per line, `#` comments allowed). This module turns those declarations into
small version-independent launchers. No subprocess or network here; the CLI and the hook call it.
"""
import os
import re

MARKER = "haiggoh-shim"
PREFIX = "haiggoh-"
POLICIES = ("skip", "overwrite", "prefix")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def shim_dir():
    return os.environ.get("GET_HAIGGOH_SHIM_DIR") or os.path.expanduser("~/.local/bin")


def backup_dir():
    return (os.environ.get("GET_HAIGGOH_SHIM_BACKUP_DIR")
            or os.path.expanduser("~/.local/state/get-haiggoh/shim-backups"))


def valid_name(name):
    """A bare command name: no path separators, no leading dash or dot, no whitespace. A
    `shortcuts` file is plugin-controlled text, so it must never be able to name a path."""
    return bool(_NAME.fullmatch(name or ""))


def read_shortcuts(plugin_root):
    """Command names the plugin declares AND really ships: valid bare name, and bin/<name> is an
    executable file. Anything else is dropped silently (a stale declaration must not break apply)."""
    if not plugin_root:
        return []
    try:
        with open(os.path.join(plugin_root, "shortcuts")) as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        name = line.split("#", 1)[0].strip()
        if not name or not valid_name(name) or name in out:
            continue
        target = os.path.join(plugin_root, "bin", name)
        if os.path.isfile(target) and os.access(target, os.X_OK):
            out.append(name)
    return out


def wanted(installed):
    """[(plugin, command)] over every installed plugin, sorted by plugin name."""
    out = []
    for plugin in sorted(installed):
        for command in read_shortcuts(installed[plugin].get("installPath")):
            out.append((plugin, command))
    return out
