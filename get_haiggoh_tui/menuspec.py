"""get_haiggoh_tui.menuspec — menu-spec v1 validation, argv building, version-gated probing.

Task 6 of docs/superpowers/plans/2026-11-08-tui-01-get-haiggoh-tui.md. The contract itself
lives in docs/menu-spec.md (Plan 3's input). NEVER probe an item with --menu-spec below
its declared spec_min_version — a legacy script can read an unknown flag as a destination
and write (measured shape: backup.sh reading --menu-spec as a dir).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Literal

from .inventory import Row

BACK_LABEL = "👨🏻‍💻 Back to Get Haiggoh"
MENU_SPEC_VERSION = 1
_PROMPT_TYPES = ("choice", "text", "confirm")
_OUTPUT_MODES = ("panel", "terminal")
_PLACEHOLDER_RE = re.compile(r"^\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def _core():
    import get_haiggoh_core as c
    return c


def _ge(installed: str | None, minimum: str) -> bool:
    """installed >= minimum on dotted-numeric versions (zero-padded); False when either
    side is unparseable — an unknown installed version never earns a probe."""
    c = _core()
    left, right = c.parse_version(installed or ""), c.parse_version(minimum)
    if left is None or right is None:
        return False
    width = max(len(left), len(right))
    left += (0,) * (width - len(left))
    right += (0,) * (width - len(right))
    return left >= right


def validate(spec: dict) -> list[str]:
    """Error list for a menu-spec dict (empty = valid). Checks: menu_spec version,
    title, actions list; per action: label/argv/output; per prompt: id/question/type,
    choice requires choices; every {placeholder} needs a prompt, every prompt needs a
    placeholder."""
    errors: list[str] = []
    if not isinstance(spec, dict):
        return ["menu-spec is not a JSON object"]
    if spec.get("menu_spec") != MENU_SPEC_VERSION:
        errors.append(f"unknown menu_spec version {spec.get('menu_spec')!r} "
                      f"(this build understands {MENU_SPEC_VERSION})")
        return errors
    if not isinstance(spec.get("title"), str) or not spec.get("title"):
        errors.append("title must be a non-empty string")
    actions = spec.get("actions")
    if not isinstance(actions, list):
        errors.append("actions must be a list")
        return errors
    for i, action in enumerate(actions):
        where = f"action[{i}]"
        if not isinstance(action, dict):
            errors.append(f"{where}: not an object")
            continue
        if not isinstance(action.get("label"), str) or not action.get("label"):
            errors.append(f"{where}: label must be a non-empty string")
        argv = action.get("argv")
        if not isinstance(argv, list) or not all(isinstance(t, str) for t in argv):
            errors.append(f"{where}: argv must be a list of strings")
            argv = []
        if action.get("output") not in _OUTPUT_MODES:
            errors.append(f"{where}: output must be one of {list(_OUTPUT_MODES)}")
        prompts = action.get("prompts", [])
        if not isinstance(prompts, list):
            errors.append(f"{where}: prompts must be a list")
            prompts = []
        prompt_ids: set[str] = set()
        for j, prompt in enumerate(prompts):
            pwhere = f"{where}.prompts[{j}]"
            if not isinstance(prompt, dict):
                errors.append(f"{pwhere}: not an object")
                continue
            pid = prompt.get("id")
            if not isinstance(pid, str) or not pid:
                errors.append(f"{pwhere}: id must be a non-empty string")
                continue
            prompt_ids.add(pid)
            if not isinstance(prompt.get("question"), str):
                errors.append(f"{pwhere}: question must be a string")
            ptype = prompt.get("type")
            if ptype not in _PROMPT_TYPES:
                errors.append(f"{pwhere}: type must be one of {list(_PROMPT_TYPES)}")
            if ptype == "choice" and not isinstance(prompt.get("choices"), list):
                errors.append(f"{pwhere}: type 'choice' requires a choices list")
        placeholders = set()
        for tok in argv:
            m = _PLACEHOLDER_RE.match(tok)
            if m:
                placeholders.add(m.group(1))
        for ph in sorted(placeholders - prompt_ids):
            errors.append(f"{where}: placeholder {{{ph}}} has no prompt with that id")
        for pid in sorted(prompt_ids - placeholders):
            errors.append(f"{where}: prompt {pid!r} is not referenced by any argv placeholder")
    return errors


def build_argv(action: dict, answers: dict[str, str]) -> list[str]:
    """Substitute WHOLE-TOKEN {placeholder}s only; the result is always a list — never
    shell-joined, so an answer like 'a; rm -rf ~' stays a single argv element."""
    out: list[str] = []
    for tok in action.get("argv", []):
        m = _PLACEHOLDER_RE.match(tok)
        out.append(answers.get(m.group(1), tok) if m else tok)
    return out


def _installed_plugins() -> dict:
    c = _core()
    try:
        return c.load_installed(c.load_json(c.installed_plugins_path()))
    except Exception:
        return {}


def resolve_argv(row: Row, argv: list[str], installed: dict | None = None,
                 which=shutil.which) -> list[str] | None:
    """Make argv[0] runnable from the USER's terminal. The catalog names commands as Claude
    sees them, but a plugin's bin/ is only on Claude's Bash PATH (measured 2026-11-09:
    check-code.py and waypoints_menu.py are on no login-shell PATH). Order: the user's PATH;
    then, for a plugin row, <installPath>/bin/<name> and <installPath>/<name>. A found
    script that is not executable (the plugin cache keeps check-code.py 0644) runs through
    python3 for .py, sh for .sh. None when nothing resolves — the caller says so instead
    of crashing on FileNotFoundError."""
    if not argv:
        return None
    head, rest = argv[0], list(argv[1:])
    if os.sep not in head:
        found = which(head)
        if found:
            return [found, *rest]
    elif os.path.isfile(head):
        return list(argv)
    if row.section == "plugin" and os.sep not in head:
        if installed is None:
            installed = _installed_plugins()
        root = (installed.get(row.name) or {}).get("installPath")
        for cand in ((os.path.join(root, "bin", head), os.path.join(root, head)) if root else ()):
            if not os.path.isfile(cand):
                continue
            if os.access(cand, os.X_OK):
                return [cand, *rest]
            interp = {".py": "python3", ".sh": "sh"}.get(os.path.splitext(cand)[1])
            interp_path = which(interp) if interp else None
            if interp_path:
                return [interp_path, cand, *rest]
    return None


def menu_for(row: Row, run=subprocess.run, installed: dict | None = None, which=shutil.which
             ) -> tuple[Literal["spec", "legacy", "missing", "none"], dict | list[str] | str | None]:
    """('spec', spec) only when row.installed >= menu.spec_min_version (non-null) AND
    menu.argv + ['--menu-spec'] returns valid menu-spec JSON within 5 s; otherwise
    ('legacy', menu.argv + ['--return-to', 'get-haiggoh'] when installed >=
    return_to_min_version); ('none', None) when the row has no menu. Never probes
    below spec_min_version (zero run calls)."""
    menu = row.menu
    if not menu:
        return ("none", None)
    raw = list(menu.get("argv") or [])
    argv = resolve_argv(row, raw, installed=installed, which=which)
    if argv is None:
        return ("missing", f"{row.name}: can't find {raw[0] if raw else 'its menu command'} "
                           "on PATH or in the installed plugin — try updating it")
    spec_min = menu.get("spec_min_version")
    return_min = menu.get("return_to_min_version")
    if spec_min is not None and _ge(row.installed, spec_min):
        try:
            r = run(argv + ["--menu-spec"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                spec = json.loads(r.stdout)
                if not validate(spec):
                    return ("spec", spec)
        except Exception:
            pass  # probe failure -> legacy fallback, nothing is blocked
    legacy = list(argv)
    if return_min is not None and _ge(row.installed, return_min):
        legacy += ["--return-to", "get-haiggoh"]
    return ("legacy", legacy)


def actions_with_back(spec: dict) -> list[dict]:
    """The spec's actions with the Back item appended LAST (the caller only calls this
    when the menu was opened from get-haiggoh)."""
    back = {"label": BACK_LABEL, "argv": [], "output": "panel", "prompts": []}
    return list(spec.get("actions", [])) + [back]
