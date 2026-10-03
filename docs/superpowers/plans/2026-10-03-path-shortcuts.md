# PATH shortcuts for haiggoh plugin CLIs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This plan also follows `~/.claude/plans/_PLAYBOOKS/Playbook_AI-Targeted_Execution_Plan_v4.md`: forced preflight, authority matrix, receipts, adversarial review.

**Goal:** After `get-haiggoh apply` (or its new alias `upgrade`), every participating haiggoh plugin CLI is reachable by bare name in the user's own shell, survives plugin updates, and never overwrites an existing command without consent.

**Architecture:** get-haiggoh owns one shim installer (`get_haiggoh_shims.py`). Each plugin declares its commands in a plain-text `shortcuts` file at its root. The installer writes version-independent bash shims into `~/.local/bin`; a shim resolves the plugin's `installPath` from `installed_plugins.json` at run time and `exec`s `bin/<name>`. Collisions default to skip-and-report, with `overwrite` (backed up first) and `prefix` as explicit choices.

**Tech Stack:** Python 3 stdlib only, bash shims, pytest (pipx: `~/.local/bin/pytest`; the default `python3` has NO pytest).

**Spec:** `docs/superpowers/specs/2026-10-03-path-shortcuts-design.md` (approved by the user 2026-10-03; the two open questions were answered "yes, yes").

## Global Constraints

- **free-agents repo is OFF LIMITS** (mid-merge across working trees, user instruction 2026-10-03). No file there is read for editing, created, or committed. `csl` gets no shortcut in this pass.
- `upgrade` is an alias of `apply`. A bare `get-haiggoh` opens the interactive menu.
- Shims live in `~/.local/bin` (override `GET_HAIGGOH_SHIM_DIR`). A shim is a regular file whose line 2 starts with `# haiggoh-shim`.
- Collision default is `skip` (reported with the alternatives). `overwrite` records the previous link target or file under `~/.local/state/get-haiggoh/shim-backups/` (override `GET_HAIGGOH_SHIM_BACKUP_DIR`) BEFORE replacing it.
- The installed record (`installed_plugins.json` `installPath`) is authoritative for resolution; the highest numeric version directory under the cache is only a fallback.
- Every script supports `--help` that documents commands and env vars. An unknown flag exits non-zero with a usage line on stderr.
- Shortcut names must match `[A-Za-z0-9][A-Za-z0-9._-]*` (no path separators).
- Versions: get-haiggoh 0.7.0→0.8.0, waypoints 0.12.0→0.13.0, resume-interrupted 0.4.1→0.5.0, lasting-plans 1.1.0→1.2.0, cost-tracker 0.9.1→0.10.0. Each bump is stated everywhere the version appears (manifest, CHANGELOG, README/VERSION file).
- Opt-out for automation: `GET_HAIGGOH_NO_SHIMS=1` disables the shim step in both `apply` and the SessionStart hook.
- Stage commits BY PATH; never `git add -A`; never bare `git stash`.

## Review Focus

- A `shortcuts` entry like `../../x` or `a/b` must be rejected, never written as a path. (Task 1)
- The existing `~/.local/bin/waypoints` is a symlink; writing "through" it would corrupt the agy script. The overwrite must REPLACE the link. (Task 3)
- `~/.local/bin` may contain huge binaries (`joyia` is 71 MB); the "is this our shim" check must read a few bytes, not a line. (Task 3)
- Home or cache paths may contain a space; the shim must still resolve and exec. (Task 2)
- A plugin can be installed with a `shortcuts` entry whose `bin/<name>` is missing or non-executable; it must be ignored, not shimmed. (Task 1)
- The hook must add shims even when the marketplace is unregistered or the daily refresh failed. (Task 6)

## Credit-efficient offload (CLAUDE.md requirement)

- Tasks 1–6 and 7: `cloud:spec` — new design-coupled code whose tests are being written at the same time; expires when Task 6 lands and the interface is frozen.
- Task 8 (four near-identical repo edits: a `shortcuts` file, one test, a version bump, a changelog line): `local:operator` is appropriate. It is mechanical, each output is checkable by its own test, and the diff is small enough to review. Dispatch via `curl` to the local endpoint resolved with `la-roles.sh`, not the Agent tool.
- Task 9 (live machine changes): `cloud:` — touches the user's real `~/.local/bin` and needs a human-visible plan first; expires after rollout.

## Authority matrix

| Operation | Status | Gate |
|---|---|---|
| Read-only inspection of all repos listed here | Allowed now | n/a |
| Edit files in worktrees `get-haiggoh-shortcuts` and the four `*-shortcut` worktrees | Allowed now | dirty-work check in Phase 0 |
| Edit the main checkouts of any repo | Prohibited | use worktrees |
| Any read-for-edit, write, branch or commit in **free-agents** | **Prohibited** | user instruction 2026-10-03 |
| Run synthetic tests (temp dirs, fake plugins) | Allowed now | never point tests at the real `~/.local/bin` |
| Commit on feature branches, staged by path | Allowed after that task's tests pass | staged-diff review |
| Push a feature branch | Requires separate user permission | not granted |
| Merge to main / tag / release / `claude plugin update` | Requires separate user permission | not granted; permission to push does not cover it |
| Write to the real `~/.local/bin`, replace the four `agy-*` symlinks | Allowed only in Task 9, after the plan output is shown and the user confirms | user said "overwrite those" on 2026-10-03, but confirm at run time |
| Delete anything | Prohibited | backups are additive |

## Phase 0 — forced preflight (Task 0)

**Three sentences FIRST (before any edit):** state in exactly three sentences how Task 1 (shortcut discovery) feeds Task 2 (the shim), Task 3 (collision-aware install), and finally the CLI and hook that users actually touch. Then do read-only discovery.

- [ ] **Step 1: Verify the writable source and branch**

Run: `git -C ~/ClaudeWorkspace/get-haiggoh-shortcuts branch --show-current && git -C ~/ClaudeWorkspace/get-haiggoh-shortcuts status --short`
Expected: `feature/path-shortcuts`; the only untracked paths are under `docs/superpowers/` (the spec and this plan). If anything else is dirty, stop and ask.

- [ ] **Step 2: Baseline tests**

Run: `cd ~/ClaudeWorkspace/get-haiggoh-shortcuts && ~/.local/bin/pytest tests -q 2>&1 | tail -4`
Expected on 2026-10-03: `1 failed, 71 passed`. The one failure, `test_hook_never_shells_out_to_git_ls_remote`, times out after 10 s and ALSO fails on the untouched `get-haiggoh` main checkout, so it predates this work. Hypothesis (unverified): the hook reaches the network for the installed `measure-twice` because the test does not set `GET_HAIGGOH_SKIP_REMOTE_VERSION_CHECK`. Do NOT fix it in this branch; report it in the final review. Every later receipt must show "71 original passed + N new passed, same 1 pre-existing failure".

- [ ] **Step 3: Discover the unknowns**

1. `ls ~/.claude/plugins/cache/haiggoh/get-haiggoh/` shows `0.5.2`, `0.7.0`, `1.0.0` while the record says `0.7.0`. Find where `1.0.0` came from: `git -C ~/ClaudeWorkspace/get-haiggoh tag`, and `grep -n version ~/.claude/plugins/cache/haiggoh/get-haiggoh/1.0.0/.claude-plugin/plugin.json`. Record the answer in the receipt; it does not change the design (the record wins) but it explains the stale directory.
2. `grep -rn "0\.7\.0" ~/ClaudeWorkspace/get-haiggoh-shortcuts --include='*.md' --include='*.json' --include='*.py' -l` to list every place the version is stated.
3. Read `.claude-plugin/marketplace.json` and note whether it carries per-plugin versions.
4. `sed -n 60,130p ~/ClaudeWorkspace/cost-tracker/install.sh`: cost-tracker's installer links `~/.local/bin/cost-tracker` to its checkout and reports a non-symlink as "FOREIGN". Record how it treats a haiggoh shim. Do NOT edit `install.sh`.
5. Confirm `bin/get-haiggoh-menu` and `bin/get-haiggoh.py` are executable (`ls -l bin`).

**🧪 Receipt 0:** paste the outputs of steps 1–5, the 3 sentences, and the baseline summary line.

---

## Task 1: Shortcut discovery and name validation

**Files:**
- Create: `get_haiggoh_shims.py`
- Modify: `tests/conftest.py`
- Create: `tests/test_shims.py`

**Interfaces:**
- Produces: `shim_dir() -> str`, `backup_dir() -> str`, `valid_name(name: str) -> bool`, `read_shortcuts(plugin_root: str|None) -> list[str]`, `wanted(installed: dict) -> list[tuple[str, str]]` where `installed` is the output of `c.load_installed` (`{plugin: {"version", "installPath"}}`).
- Consumes: `get_haiggoh_core.load_installed`.

- [ ] **Step 1: Add test isolation and the fake-machine fixture**

Replace the whole of `tests/conftest.py` (it is 4 lines; read it first) with:

```python
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import get_haiggoh_core as c  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_shim_dirs(tmp_path_factory, monkeypatch):
    """No test may ever touch the real ~/.local/bin or the real backup dir, even by accident."""
    base = tmp_path_factory.mktemp("shim-isolation")
    monkeypatch.setenv("GET_HAIGGOH_SHIM_DIR", str(base / "bin"))
    monkeypatch.setenv("GET_HAIGGOH_SHIM_BACKUP_DIR", str(base / "backups"))


class World:
    """A fake machine under tmp_path. The directory name contains a SPACE on purpose."""

    def __init__(self, tmp_path, monkeypatch):
        self.home = tmp_path / "my home"
        self.bin = self.home / "bin"
        self.backups = self.home / "backups"
        self.cache = self.home / "cache" / "haiggoh"
        self.record = self.home / "installed_plugins.json"
        self.bin.mkdir(parents=True)
        self.paths = {}
        for key, value in self.env_overrides().items():
            monkeypatch.setenv(key, value)

    def env_overrides(self):
        return {
            "GET_HAIGGOH_SHIM_DIR": str(self.bin),
            "GET_HAIGGOH_SHIM_BACKUP_DIR": str(self.backups),
            "GET_HAIGGOH_INSTALLED_PLUGINS_FILE": str(self.record),
            "GET_HAIGGOH_CACHE_DIR": str(self.cache),
            "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": str(self.home / "no-marketplaces.json"),
            "GET_HAIGGOH_SKIP_FILE": str(self.home / "skip.json"),
            "GET_HAIGGOH_REFRESH_STAMP_FILE": str(self.home / "stamp.json"),
            "GET_HAIGGOH_SKIP_REMOTE_VERSION_CHECK": "1",
            "GET_HAIGGOH_SKIP_NETWORK_REFRESH": "1",
        }

    def plugin(self, name, version, commands, declare=True, executable=True):
        root = self.cache / name / version
        (root / "bin").mkdir(parents=True)
        for cmd in commands:
            script = root / "bin" / cmd
            script.write_text(f'#!/usr/bin/env bash\necho "{name}-{version}:{cmd}:$*"\n')
            script.chmod(0o755 if executable else 0o644)
        if declare:
            (root / "shortcuts").write_text("# shortcuts\n" + "\n".join(commands) + "\n")
        self.paths[name] = str(root)
        self.write_record()
        return root

    def write_record(self):
        plugins = {f"{n}@haiggoh": [{"version": os.path.basename(p), "installPath": p}]
                   for n, p in self.paths.items()}
        self.record.write_text(json.dumps({"plugins": plugins}))

    def installed(self):
        return c.load_installed(c.load_json(str(self.record)))

    def env(self):
        env = os.environ.copy()
        env.update(self.env_overrides())
        return env


@pytest.fixture
def world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_shims.py`:

```python
import os

import pytest

import get_haiggoh_shims as s


@pytest.mark.parametrize("name", ["waypoints", "get-haiggoh", "a.b_c", "x1"])
def test_valid_names(name):
    assert s.valid_name(name)


@pytest.mark.parametrize("name", ["", ".", "..", "../x", "a/b", "-rf", " x", "x y", "/abs"])
def test_invalid_names(name):
    assert not s.valid_name(name)


def test_read_shortcuts_returns_declared_real_executables(world):
    root = world.plugin("waypoints", "0.12.0", ["waypoints"])
    assert s.read_shortcuts(str(root)) == ["waypoints"]


def test_read_shortcuts_ignores_comments_blanks_duplicates_and_bad_names(world):
    root = world.plugin("p", "1.0.0", ["real"], declare=False)
    (root / "shortcuts").write_text("# header\n\nreal  # trailing\nreal\n../real\na/b\nmissing\n")
    assert s.read_shortcuts(str(root)) == ["real"]


def test_read_shortcuts_ignores_non_executable_target(world):
    root = world.plugin("p", "1.0.0", ["tool"], executable=False)
    assert s.read_shortcuts(str(root)) == []


def test_read_shortcuts_handles_missing_file_and_none(world):
    root = world.plugin("p", "1.0.0", ["tool"], declare=False)
    assert s.read_shortcuts(str(root)) == []
    assert s.read_shortcuts(None) == []


def test_wanted_lists_pairs_in_plugin_order(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    world.plugin("cost-tracker", "0.9.1", ["cost-tracker"])
    assert s.wanted(world.installed()) == [("cost-tracker", "cost-tracker"),
                                           ("waypoints", "waypoints")]
```

- [ ] **Step 3: Run to verify failure**

Run: `cd ~/ClaudeWorkspace/get-haiggoh-shortcuts && ~/.local/bin/pytest tests/test_shims.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'get_haiggoh_shims'`.

- [ ] **Step 4: Implement**

Create `get_haiggoh_shims.py`:

```python
"""PATH shims for haiggoh plugin CLIs.

Design: docs/superpowers/specs/2026-10-03-path-shortcuts-design.md. A plugin declares the
commands it wants on the user's shell PATH in a plain-text `shortcuts` file at its root (one
bare command name per line, `#` comments allowed). This module turns those declarations into
small version-independent launchers. No subprocess or network here; the CLI and the hook call it.
"""
import os
import re
import shutil
import time

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
```

- [ ] **Step 5: Run to verify pass**

Run: `~/.local/bin/pytest tests/test_shims.py -q`
Expected: all pass.

- [ ] **Step 6: Discriminant**

Commit first (Step 7), then temporarily change `_NAME` to `r".*"`, run `~/.local/bin/pytest tests/test_shims.py -q -k invalid`, expect FAILURES on `../x`, `a/b`, `/abs`; restore with `git checkout -- get_haiggoh_shims.py` and rerun to see pass.

- [ ] **Step 7: Commit**

```bash
git add get_haiggoh_shims.py tests/conftest.py tests/test_shims.py
git commit -m "feat(shims): shortcut discovery with name validation and test isolation"
```
(End the message with the attribution line from the session's system reminder.)

**🧪 Receipt 1:** pytest summary for `tests/test_shims.py`; the failing output from the mutation and the passing rerun; full-suite line "71 + N passed, same 1 pre-existing failure".

---

## Task 2: The shim — version-independent resolution

**Files:**
- Modify: `get_haiggoh_shims.py` (append)
- Modify: `tests/test_shims.py` (append)

**Interfaces:**
- Produces: `render_shim(plugin: str, command: str) -> str`. The output starts with `#!/usr/bin/env bash`, line 2 is `# haiggoh-shim plugin=<plugin> command=<command>`.
- Resolution order at run time: (1) `installPath` from `$GET_HAIGGOH_INSTALLED_PLUGINS_FILE` (default `~/.claude/plugins/installed_plugins.json`) if `<installPath>/bin/<command>` is executable; (2) the highest numeric version directory under `$GET_HAIGGOH_CACHE_DIR/<plugin>/` (default `~/.claude/plugins/cache/haiggoh`) that contains an executable `bin/<command>`; (3) exit 127 with a message on stderr.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_shims.py`)

```python
import subprocess


def _install_shim(world, plugin, command):
    path = world.bin / command
    path.write_text(s.render_shim(plugin, command))
    path.chmod(0o755)
    return path


def _run(shim, world, *args):
    return subprocess.run([str(shim), *args], capture_output=True, text=True,
                          env=world.env(), timeout=20)


def test_render_shim_has_shebang_and_marker_on_line_two():
    lines = s.render_shim("waypoints", "waypoints").splitlines()
    assert lines[0] == "#!/usr/bin/env bash"
    assert lines[1] == "# haiggoh-shim plugin=waypoints command=waypoints"


def test_shim_runs_installed_plugin_and_forwards_arguments(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    r = _run(_install_shim(world, "waypoints", "waypoints"), world, "list", "--gated")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "waypoints-0.12.0:waypoints:list --gated"


def test_shim_follows_a_version_bump_without_being_regenerated(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    shim = _install_shim(world, "waypoints", "waypoints")
    assert "0.12.0" in _run(shim, world).stdout
    world.plugin("waypoints", "0.13.0", ["waypoints"])  # new version dir + record now points at it
    assert "0.13.0" in _run(shim, world).stdout


def test_record_wins_over_a_higher_stale_cache_directory(world):
    world.plugin("get-haiggoh", "0.7.0", ["get-haiggoh"])
    stale = world.cache / "get-haiggoh" / "1.0.0" / "bin"
    stale.mkdir(parents=True)
    (stale / "get-haiggoh").write_text('#!/usr/bin/env bash\necho STALE\n')
    (stale / "get-haiggoh").chmod(0o755)
    r = _run(_install_shim(world, "get-haiggoh", "get-haiggoh"), world)
    assert "0.7.0" in r.stdout and "STALE" not in r.stdout


def test_fallback_picks_highest_numeric_version_when_record_missing(world):
    world.plugin("p", "1.9.0", ["p"])
    world.plugin("p", "1.10.0", ["p"])   # lexically smaller than 1.9.0, numerically larger
    world.record.write_text("{}")
    r = _run(_install_shim(world, "p", "p"), world)
    assert "1.10.0" in r.stdout, r.stdout + r.stderr


def test_shim_exits_127_with_a_hint_when_plugin_is_not_installed(world):
    r = _run(_install_shim(world, "ghost", "ghost"), world)
    assert r.returncode == 127
    assert "not installed" in r.stderr and "get-haiggoh apply" in r.stderr
```

- [ ] **Step 2: Run to verify failure**

Run: `~/.local/bin/pytest tests/test_shims.py -q -k "shim or fallback or record"`
Expected: FAIL with `AttributeError: module 'get_haiggoh_shims' has no attribute 'render_shim'`.

- [ ] **Step 3: Implement** (append to `get_haiggoh_shims.py`)

The template has no single quotes inside the python block (it sits in a single-quoted `python3 -c '...'`), and uses `sys.argv` for the two names, so nothing is interpolated into code.

```python
_SHIM = """#!/usr/bin/env bash
# haiggoh-shim plugin=__PLUGIN__ command=__COMMAND__
# Generated by get-haiggoh. Resolves the installed plugin at run time, so plugin updates never
# break it. Regenerate with: get-haiggoh shims apply
root="$(python3 -c '
import json, os, sys
plugin, command = sys.argv[1], sys.argv[2]
record = os.environ.get("GET_HAIGGOH_INSTALLED_PLUGINS_FILE") or os.path.expanduser("~/.claude/plugins/installed_plugins.json")
cache = os.environ.get("GET_HAIGGOH_CACHE_DIR") or os.path.expanduser("~/.claude/plugins/cache/haiggoh")
def ok(p):
    return bool(p) and os.access(os.path.join(p, "bin", command), os.X_OK)
try:
    for e in json.load(open(record)).get("plugins", {}).get(plugin + "@haiggoh", []):
        if ok(e.get("installPath")):
            print(e["installPath"])
            sys.exit(0)
except Exception:
    pass
def key(v):
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return ()
base = os.path.join(cache, plugin)
for v in sorted(os.listdir(base) if os.path.isdir(base) else [], key=key, reverse=True):
    if ok(os.path.join(base, v)):
        print(os.path.join(base, v))
        break
' __PLUGIN__ __COMMAND__)"
if [ -z "$root" ]; then
  echo "__COMMAND__: the haiggoh plugin __PLUGIN__ is not installed (run: get-haiggoh apply)" >&2
  exit 127
fi
exec "$root/bin/__COMMAND__" "$@"
"""


def render_shim(plugin, command):
    """Shim text for one command. Both names were validated by valid_name(), which excludes every
    character that is special to bash, so plain substitution cannot inject code."""
    if not (valid_name(plugin) and valid_name(command)):
        raise ValueError(f"unsafe shim name: {plugin!r} / {command!r}")
    return _SHIM.replace("__PLUGIN__", plugin).replace("__COMMAND__", command)
```

- [ ] **Step 4: Run to verify pass**

Run: `~/.local/bin/pytest tests/test_shims.py -q`
Expected: all pass (including the "my home" path with a space).

- [ ] **Step 5: Discriminant (mutation)**

Commit (Step 6). Then in `_SHIM`, change `reverse=True` to `reverse=False` and rerun `-k fallback`: expect FAIL. Then delete the whole `try:` record loop (so the cache sort runs first), rerun `-k record_wins`: expect FAIL. Restore with `git checkout -- get_haiggoh_shims.py`; rerun: pass.

- [ ] **Step 6: Commit**

```bash
git add get_haiggoh_shims.py tests/test_shims.py
git commit -m "feat(shims): version-independent shim resolved from the installed record"
```

**🧪 Receipt 2:** pytest summary; both mutation failures and the restored pass; one manual run of a generated shim against the fake plugin showing stdout `waypoints-0.12.0:waypoints:list --gated`.

---

## Task 3: Collision-aware plan and apply

**Files:**
- Modify: `get_haiggoh_shims.py` (append)
- Modify: `tests/test_shims.py` (append)

**Interfaces:**
- Produces:
  - `is_our_shim(path) -> bool`
  - `plan_shims(installed, policy="skip", directory=None) -> list[dict]`; each action dict has keys `plugin, command, name, path, text, state, action, detail`. `action` is one of `create, refresh, noop, overwrite, skip`.
  - `apply_action(act) -> dict` (adds `backup` for overwrites)
  - `on_path(directory) -> bool`
  - `format_report(actions, directory, applied) -> str`
- Consumes: `wanted`, `render_shim`, `shim_dir`, `backup_dir`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_shims.py`)

```python
def _apply(world, policy="skip"):
    acts = s.plan_shims(world.installed(), policy=policy, directory=str(world.bin))
    for a in acts:
        s.apply_action(a)
    return acts


def test_create_writes_an_executable_shim_that_runs(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    acts = _apply(world)
    assert [a["action"] for a in acts] == ["create"]
    shim = world.bin / "waypoints"
    assert os.access(shim, os.X_OK) and s.is_our_shim(str(shim))
    assert "waypoints-0.12.0" in _run(shim, world).stdout


def test_second_apply_is_a_noop(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    _apply(world)
    before = (world.bin / "waypoints").stat().st_mtime_ns
    acts = _apply(world)
    assert [a["action"] for a in acts] == ["noop"]
    assert (world.bin / "waypoints").stat().st_mtime_ns == before


def test_stale_shim_is_refreshed(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    _apply(world)
    shim = world.bin / "waypoints"
    shim.write_text(shim.read_text() + "# drift\n")
    assert [a["action"] for a in _apply(world)] == ["refresh"]
    assert "drift" not in shim.read_text()


def test_skip_leaves_a_foreign_symlink_untouched_and_explains(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    agy = world.home / "agy-waypoints"
    agy.write_text("agy\n")
    (world.bin / "waypoints").symlink_to(agy)
    acts = _apply(world, "skip")
    assert acts[0]["action"] == "skip" and "symlink" in acts[0]["detail"]
    assert (world.bin / "waypoints").is_symlink()
    report = s.format_report(acts, str(world.bin), applied=True)
    assert "SKIPPED" in report and "--on-collision=overwrite" in report and "--on-collision=prefix" in report


def test_overwrite_replaces_the_link_without_writing_through_it(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    agy = world.home / "agy-waypoints"
    agy.write_text("#!/bin/sh\necho agy\n")
    (world.bin / "waypoints").symlink_to(agy)
    acts = _apply(world, "overwrite")
    link = world.bin / "waypoints"
    assert acts[0]["action"] == "overwrite"
    assert not link.is_symlink() and s.is_our_shim(str(link))
    assert agy.read_text() == "#!/bin/sh\necho agy\n"          # write-through would clobber this
    backups = list(world.backups.iterdir())
    assert len(backups) == 1 and backups[0].read_text().strip() == str(agy)
    assert acts[0]["backup"] == str(backups[0])


def test_overwrite_of_a_regular_file_keeps_an_identical_backup(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    (world.bin / "waypoints").write_text("#!/bin/sh\necho mine\n")
    _apply(world, "overwrite")
    backups = list(world.backups.iterdir())
    assert len(backups) == 1 and backups[0].read_text() == "#!/bin/sh\necho mine\n"


def test_prefix_installs_haiggoh_name_and_leaves_the_original(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    (world.bin / "waypoints").write_text("mine\n")
    acts = _apply(world, "prefix")
    assert acts[0]["action"] == "create" and acts[0]["name"] == "haiggoh-waypoints"
    assert (world.bin / "waypoints").read_text() == "mine\n"
    assert "waypoints-0.12.0" in _run(world.bin / "haiggoh-waypoints", world).stdout


def test_prefix_skips_when_the_prefixed_name_is_taken_too(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    (world.bin / "waypoints").write_text("mine\n")
    (world.bin / "haiggoh-waypoints").write_text("also mine\n")
    acts = _apply(world, "prefix")
    assert acts[0]["action"] == "skip" and (world.bin / "haiggoh-waypoints").read_text() == "also mine\n"


def test_directory_in_the_way_is_skipped_even_under_overwrite(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    (world.bin / "waypoints").mkdir()
    acts = _apply(world, "overwrite")
    assert acts[0]["action"] == "skip" and (world.bin / "waypoints").is_dir()


def test_two_plugins_declaring_one_name_second_is_skipped(world):
    world.plugin("a-plugin", "1.0.0", ["tool"])
    world.plugin("b-plugin", "1.0.0", ["tool"])
    acts = _apply(world)
    assert [a["action"] for a in acts] == ["create", "skip"]
    assert "a-plugin" in acts[1]["detail"]


def test_is_our_shim_reads_bytes_not_lines(world):
    big = world.bin / "joyia"
    big.write_bytes(b"\x00" * 5_000_000)   # a huge binary with no newline
    assert s.is_our_shim(str(big)) is False


def test_unknown_policy_is_rejected(world):
    with pytest.raises(ValueError):
        s.plan_shims(world.installed(), policy="nuke", directory=str(world.bin))
```

- [ ] **Step 2: Run to verify failure**

Run: `~/.local/bin/pytest tests/test_shims.py -q`
Expected: the new tests FAIL with `AttributeError ... 'plan_shims'` / `'is_our_shim'`.

- [ ] **Step 3: Implement** (append to `get_haiggoh_shims.py`)

```python
def is_our_shim(path):
    """True only for a REGULAR file (never a symlink) whose line 2 is our marker. Reads 256 bytes:
    ~/.local/bin holds multi-megabyte binaries with no newline, and a line read would slurp them."""
    try:
        if os.path.islink(path) or not os.path.isfile(path):
            return False
        with open(path, "rb") as f:
            head = f.read(256).decode("utf-8", "replace").splitlines()
    except OSError:
        return False
    return len(head) > 1 and head[1].startswith("# " + MARKER)


def _decide(path, text):
    """-> (state, action, detail) for ONE target path. `collision` means: taken by something that
    is not ours; the caller's policy decides what happens next."""
    if not os.path.lexists(path):
        return "absent", "create", ""
    if os.path.isdir(path) and not os.path.islink(path):
        return "foreign", "skip", "is a directory"
    if is_our_shim(path):
        with open(path) as f:
            same = f.read() == text
        return ("current", "noop", "") if same else ("stale", "refresh", "")
    kind = f"symlink -> {os.readlink(path)}" if os.path.islink(path) else "regular file"
    return "foreign", "collision", f"exists and is not a haiggoh shim ({kind})"


def plan_shims(installed, policy="skip", directory=None):
    """Decide, WITHOUT touching the disk, what each wanted shortcut needs."""
    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {POLICIES}, got {policy!r}")
    directory = directory or shim_dir()
    actions, claimed = [], {}
    for plugin, command in wanted(installed):
        text = render_shim(plugin, command)
        name = command
        path = os.path.join(directory, name)
        act = {"plugin": plugin, "command": command, "name": name, "path": path, "text": text}
        if name in claimed:
            act.update(state="duplicate", action="skip",
                       detail=f"also declared by {claimed[name]}, which came first")
            actions.append(act)
            continue
        claimed[name] = plugin
        state, action, detail = _decide(path, text)
        if action == "collision":
            if policy == "overwrite":
                action = "overwrite"
            elif policy == "prefix":
                name = PREFIX + command
                path = os.path.join(directory, name)
                state2, action2, detail2 = _decide(path, text)
                if action2 == "collision":
                    action, detail = "skip", f"{name} is taken too ({detail2})"
                else:
                    state, action, detail = state2, action2, f"{command} was taken ({detail}); using {name}"
            else:
                action = "skip"
        act.update(name=name, path=path, state=state, action=action, detail=detail)
        actions.append(act)
    return actions


def _backup(path):
    """Record what is about to be replaced. A symlink is recorded as its target text (restore with
    `ln -sfn "$(cat FILE)" PATH`); a regular file is copied with its mode. Raises on failure, which
    aborts the overwrite: no backup, no replace."""
    os.makedirs(backup_dir(), exist_ok=True)
    base = os.path.join(backup_dir(), f"{os.path.basename(path)}.{time.strftime('%Y%m%d-%H%M%S')}")
    suffix = ".link" if os.path.islink(path) else ".bak"
    dest, n = base + suffix, 1
    while os.path.lexists(dest):
        dest, n = f"{base}-{n}{suffix}", n + 1
    if os.path.islink(path):
        with open(dest, "w") as f:
            f.write(os.readlink(path) + "\n")
    else:
        shutil.copy2(path, dest)
    return dest


def apply_action(act):
    """Carry out one planned action. Writes a temp file in the same directory and os.replace()s it
    over the target, which replaces a symlink ITSELF instead of writing through it into whatever
    it points at."""
    if act["action"] not in ("create", "refresh", "overwrite"):
        return act
    path = act["path"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if act["action"] == "overwrite":
        act["backup"] = _backup(path)
    tmp = f"{path}.haiggoh-tmp-{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o755)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(act["text"])
        os.chmod(tmp, 0o755)
        os.replace(tmp, path)
    finally:
        if os.path.lexists(tmp):
            os.remove(tmp)
    return act


def on_path(directory):
    real = os.path.realpath(directory)
    return real in [os.path.realpath(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p]


_VERBS = {"create": ("would create", "created"), "refresh": ("would refresh", "refreshed"),
          "noop": ("current", "current"), "overwrite": ("would OVERWRITE", "OVERWROTE"),
          "skip": ("SKIPPED", "SKIPPED")}


def format_report(actions, directory, applied):
    lines = [f"PATH shortcuts in {directory}:"]
    if not actions:
        lines.append("  (no installed haiggoh plugin declares a shortcut)")
    for a in actions:
        verb = _VERBS[a["action"]][1 if applied else 0]
        extra = ""
        if a["action"] == "skip":
            extra = (f": {a['detail']}. Options: --on-collision=overwrite (the old one is backed up "
                     f"first) or --on-collision=prefix (installs {PREFIX}{a['command']})")
        elif a["action"] == "overwrite":
            extra = f" (was: {a['detail']}" + (f"; backup {a['backup']})" if a.get("backup") else ")")
        elif a["detail"]:
            extra = f" ({a['detail']})"
        lines.append(f"  {a['name']:<18} {verb}  [{a['plugin']}]{extra}")
    if actions and not on_path(directory):
        lines.append(f"  warning: {directory} is not on your PATH, so these names will not resolve yet")
    return "\n".join(lines)
```

- [ ] **Step 4: Run to verify pass**

Run: `~/.local/bin/pytest tests/test_shims.py -q`
Expected: all pass.

- [ ] **Step 5: Discriminants**

Commit (Step 6) first. Then, in `apply_action`, replace the tmp-file + `os.replace` block with `open(path, "w").write(act["text"])` and run `~/.local/bin/pytest tests/test_shims.py -q -k overwrite_replaces`: expect FAIL (the file the symlink points at gets clobbered). Restore with `git checkout -- get_haiggoh_shims.py` and rerun: pass.

- [ ] **Step 6: Commit**

```bash
git add get_haiggoh_shims.py tests/test_shims.py
git commit -m "feat(shims): collision-aware plan/apply with backups and replace-not-write-through"
```

**🧪 Receipt 3:** pytest summary; mutation (a) failing output and restored pass; `ls` of a backup directory from the overwrite test is not needed (tmp), but show the `.link` content assertion passing.

---

## Task 4: CLI — `upgrade`, `shims`, apply integration, help

**Files:**
- Modify: `bin/get-haiggoh.py` (replace `print_help` and `main`, lines 218–257, and `cmd_apply`'s tail)
- Create: `tests/test_shims_cli.py`

**Interfaces:**
- Consumes: `get_haiggoh_shims` (`plan_shims`, `apply_action`, `format_report`, `shim_dir`, `POLICIES`).
- Produces (CLI contract): `get-haiggoh.py plan|apply|upgrade [--only ..] [--category ..] [--on-collision skip|overwrite|prefix]`; `get-haiggoh.py shims [plan|apply] [--only ..] [--on-collision ..]` (bare `shims` = `plan`, which writes nothing).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_shims_cli.py`:

```python
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(REPO_ROOT, "bin", "get-haiggoh.py")


def run_cli(world, *args, extra_env=None):
    env = world.env()
    env.update(extra_env or {})
    return subprocess.run([sys.executable, CLI, *args], capture_output=True, text=True,
                          env=env, timeout=30)


@pytest.mark.parametrize("verb", ["apply", "upgrade"])
def test_apply_and_upgrade_both_install_shims(world, verb):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    r = run_cli(world, verb)
    assert r.returncode == 0, r.stderr
    assert "created" in r.stdout
    assert (world.bin / "waypoints").is_file()


def test_shims_plan_writes_nothing(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    r = run_cli(world, "shims", "plan")
    assert r.returncode == 0 and "would create" in r.stdout
    assert list(world.bin.iterdir()) == []


def test_bare_shims_is_a_dry_run(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    assert run_cli(world, "shims").returncode == 0
    assert list(world.bin.iterdir()) == []


def test_shims_apply_default_skips_a_collision(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    (world.bin / "waypoints").write_text("mine\n")
    r = run_cli(world, "shims", "apply")
    assert r.returncode == 0 and "SKIPPED" in r.stdout
    assert (world.bin / "waypoints").read_text() == "mine\n"


def test_shims_apply_overwrite_flag(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    (world.bin / "waypoints").write_text("mine\n")
    r = run_cli(world, "shims", "apply", "--on-collision=overwrite")
    assert r.returncode == 0 and "OVERWROTE" in r.stdout
    assert "haiggoh-shim" in (world.bin / "waypoints").read_text()
    assert len(list(world.backups.iterdir())) == 1


def test_only_limits_which_plugins_get_shims(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    world.plugin("cost-tracker", "0.9.1", ["cost-tracker"])
    run_cli(world, "shims", "apply", "--only", "waypoints")
    assert sorted(p.name for p in world.bin.iterdir()) == ["waypoints"]


def test_bad_policy_exits_2_with_usage_on_stderr(world):
    r = run_cli(world, "shims", "apply", "--on-collision=bogus")
    assert r.returncode == 2 and "on-collision" in r.stderr


def test_unknown_flag_exits_2(world):
    r = run_cli(world, "apply", "--frobnicate")
    assert r.returncode == 2 and "unrecognized" in r.stderr


def test_no_shims_env_disables_the_apply_step(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    r = run_cli(world, "apply", extra_env={"GET_HAIGGOH_NO_SHIMS": "1"})
    assert r.returncode == 0 and list(world.bin.iterdir()) == []


def test_help_documents_commands_flags_and_env(world):
    r = run_cli(world, "--help")
    assert r.returncode == 0
    for needle in ("upgrade", "shims", "--on-collision", "GET_HAIGGOH_SHIM_DIR",
                   "GET_HAIGGOH_NO_SHIMS", "GET_HAIGGOH_SHIM_BACKUP_DIR"):
        assert needle in r.stdout, needle
```

- [ ] **Step 2: Run to verify failure**

Run: `~/.local/bin/pytest tests/test_shims_cli.py -q`
Expected: FAIL (`usage: ...` exit 2 for `upgrade`/`shims`, no shims written).

- [ ] **Step 3: Implement**

Read `bin/get-haiggoh.py` fully first. Then:

(a) Change `cmd_apply`'s signature and tail. Replace `def cmd_apply(only=None, category=None):` with `def cmd_apply(only=None, category=None, policy="skip"):` and replace its final line `    return 1 if failed else 0` with:

```python
    if not os.environ.get("GET_HAIGGOH_NO_SHIMS"):
        shim_rc = cmd_shims("apply", only=only, policy=policy)
        if shim_rc:
            failed.append("shims")
    return 1 if failed else 0
```

(b) Add this function directly above `_parse_selection_args`:

```python
def cmd_shims(mode, only=None, policy="skip"):
    """Plan or create the PATH shortcuts for installed plugins (see get_haiggoh_shims)."""
    import get_haiggoh_shims as s
    installed = c.load_installed(c.load_json(c.installed_plugins_path()))
    if only:
        installed = {name: info for name, info in installed.items() if name in set(only)}
    actions = s.plan_shims(installed, policy=policy)
    try:
        if mode == "apply":
            for act in actions:
                s.apply_action(act)
    except OSError as exc:
        print(f"shims: FAILED: {exc}", file=sys.stderr)
        return 1
    print(s.format_report(actions, s.shim_dir(), applied=(mode == "apply")))
    return 0


def _parse_policy_args(argv):
    """Pull --on-collision VALUE / --on-collision=VALUE out of argv.
    Returns (policy, leftover, error_or_None)."""
    import get_haiggoh_shims as s
    policy, leftover, i = "skip", [], 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--on-collision" and i + 1 < len(argv):
            policy, i = argv[i + 1], i + 2
        elif arg.startswith("--on-collision="):
            policy, i = arg[len("--on-collision="):], i + 1
        else:
            leftover.append(arg)
            i += 1
    if policy not in s.POLICIES:
        return "skip", leftover, f"--on-collision must be one of {', '.join(s.POLICIES)} (got {policy!r})"
    return policy, leftover, None
```

(c) Replace `print_help` and `main` wholesale (they are self-contained, from `def print_help():` to just before `if __name__ == "__main__":`):

```python
def print_help():
    """Print help message."""
    print("get-haiggoh CLI - install, update and put on PATH every published haiggoh plugin")
    print("")
    print("Usage:")
    print("  get-haiggoh                       (no arguments) open the interactive menu")
    print("  get-haiggoh plan    [--only n1,n2] [--category NAME]")
    print("      Show what would be installed/updated (dry run)")
    print("  get-haiggoh apply   [--only n1,n2] [--category NAME] [--on-collision POLICY]")
    print("  get-haiggoh upgrade [...same...]   alias of apply")
    print("      Install/update plugins, then create their PATH shortcuts")
    print("  get-haiggoh shims [plan|apply] [--only n1,n2] [--on-collision POLICY]")
    print("      Only the PATH shortcuts. Bare `shims` is a dry run (same as `shims plan`)")
    print("")
    print("Options:")
    print("  --only name1,name2     Limit to specific plugin names (comma-separated)")
    print("  --category NAME        Limit to plugins in a specific category")
    print("  --on-collision POLICY  What to do when a command name is already taken by something")
    print("                         that is not a haiggoh shim: skip (default, reported),")
    print("                         overwrite (old link/file is backed up first), or")
    print("                         prefix (install it as haiggoh-<name>)")
    print("  --help                 Show this help message")
    print("")
    print("Environment:")
    print("  GET_HAIGGOH_NO_SHIMS=1            never create shortcuts (apply and the SessionStart hook)")
    print("  GET_HAIGGOH_SHIM_DIR              where shortcuts go (default ~/.local/bin)")
    print("  GET_HAIGGOH_SHIM_BACKUP_DIR       where overwritten links/files are recorded")
    print("                                    (default ~/.local/state/get-haiggoh/shim-backups)")
    print("  GET_HAIGGOH_INSTALLED_PLUGINS_FILE, GET_HAIGGOH_CACHE_DIR   override what shims resolve")
    print("")
    print("Examples:")
    print("  get-haiggoh upgrade")
    print("  get-haiggoh shims plan --on-collision=overwrite")
    print("  get-haiggoh apply --only waypoints")


def main(argv):
    if "--help" in argv:
        print_help()
        return 0

    verbs = ("plan", "apply", "upgrade", "shims")
    usage = ("usage: get-haiggoh.py plan|apply|upgrade|shims [plan|apply] [--only n1,n2] "
             "[--category NAME] [--on-collision skip|overwrite|prefix]")
    if not argv or argv[0] not in verbs:
        print(usage, file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    mode = "plan"
    if cmd == "shims":
        if rest and rest[0] in ("plan", "apply"):
            mode, rest = rest[0], rest[1:]
    only, category, leftover = _parse_selection_args(rest)
    policy, leftover, error = _parse_policy_args(leftover)
    if error:
        print(f"{usage}\n{error}", file=sys.stderr)
        return 2
    if leftover:
        print(f"{usage} (unrecognized: {' '.join(leftover)})", file=sys.stderr)
        return 2
    if cmd == "plan":
        return cmd_plan(only=only, category=category)
    if cmd == "shims":
        return cmd_shims(mode, only=only, policy=policy)
    return cmd_apply(only=only, category=category, policy=policy)   # apply and upgrade
```

Note `sys.path.insert(0, ...)` at the top of the file already makes `get_haiggoh_shims` importable.

- [ ] **Step 4: Run to verify pass**

Run: `~/.local/bin/pytest tests -q`
Expected: `1 failed` (the pre-existing one) and everything else passing.

- [ ] **Step 5: Discriminants**

Commit (Step 6). (a) Change `return cmd_apply(...)   # apply and upgrade` guard so `upgrade` falls to the usage error (e.g. remove `"upgrade"` from `verbs`): `-k upgrade` must FAIL; restore. (b) In `cmd_shims`, swap `mode == "apply"` to `True`: `test_shims_plan_writes_nothing` must FAIL; restore via `git checkout -- bin/get-haiggoh.py`.

- [ ] **Step 6: Commit**

```bash
git add bin/get-haiggoh.py tests/test_shims_cli.py
git commit -m "feat(cli): upgrade alias, shims subcommand, --on-collision, shortcuts on apply"
```

**🧪 Receipt 4:** run and paste `python3 bin/get-haiggoh.py --help` (verifying by running it, not grepping); pytest summary; both mutation failures and restored passes.

---

## Task 5: The `get-haiggoh` launcher (bare run = menu)

**Files:**
- Create: `bin/get-haiggoh` (mode 755)
- Create: `shortcuts`
- Create: `tests/test_launcher.py`

**Interfaces:**
- Produces: command `get-haiggoh`. No arguments on a terminal → `bin/get-haiggoh-menu`. No arguments without a terminal → usage on stderr, exit 2 (the menu calls `input()` and would crash on EOF). Any arguments → `bin/get-haiggoh.py` unchanged. `GET_HAIGGOH_MENU_SCRIPT` overrides the menu script (tests).

- [ ] **Step 1: Write the failing tests** — create `tests/test_launcher.py`:

```python
import os
import pty
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(REPO_ROOT, "bin", "get-haiggoh")


def test_launcher_is_executable_and_declared():
    assert os.access(LAUNCHER, os.X_OK)
    with open(os.path.join(REPO_ROOT, "shortcuts")) as f:
        assert [l.split("#")[0].strip() for l in f if l.split("#")[0].strip()] == ["get-haiggoh"]


def test_bare_run_on_a_terminal_opens_the_menu(world, tmp_path):
    fake = tmp_path / "fake-menu"
    fake.write_text("print('MENU-REACHED')\n")
    env = world.env()
    env["GET_HAIGGOH_MENU_SCRIPT"] = str(fake)
    master, slave = pty.openpty()
    try:
        r = subprocess.run([sys.executable, LAUNCHER], stdin=slave, capture_output=True,
                           text=True, env=env, timeout=15)
    finally:
        os.close(master)
        os.close(slave)
    assert r.returncode == 0 and "MENU-REACHED" in r.stdout


def test_bare_run_without_a_terminal_refuses_instead_of_crashing(world):
    r = subprocess.run([sys.executable, LAUNCHER], stdin=subprocess.DEVNULL, capture_output=True,
                       text=True, env=world.env(), timeout=15)
    assert r.returncode == 2
    assert "interactive" in r.stderr and "Traceback" not in r.stderr


def test_arguments_pass_through_to_the_cli(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    r = subprocess.run([sys.executable, LAUNCHER, "shims", "plan"], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, env=world.env(), timeout=15)
    assert r.returncode == 0 and "would create" in r.stdout


def test_help_passes_through(world):
    r = subprocess.run([sys.executable, LAUNCHER, "--help"], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, env=world.env(), timeout=15)
    assert r.returncode == 0 and "upgrade" in r.stdout
```

- [ ] **Step 2: Run to verify failure**

Run: `~/.local/bin/pytest tests/test_launcher.py -q` — Expected: FAIL (file not found / assertion).

- [ ] **Step 3: Implement**

Create `shortcuts`:

```
# Commands this plugin puts on the user's shell PATH (one bare name per line).
# get-haiggoh reads this file from every installed plugin; see docs/superpowers/specs/.
get-haiggoh
```

Create `bin/get-haiggoh`:

```python
#!/usr/bin/env python3
"""get-haiggoh -- the command. No arguments on a terminal opens the interactive menu; anything
else is handed to get-haiggoh.py unchanged (plan, apply, upgrade, shims, --help).

Env: GET_HAIGGOH_MENU_SCRIPT overrides the menu script (used by tests). See `get-haiggoh --help`
for every other variable."""
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))


def main(argv):
    if argv:
        script = os.path.join(HERE, "get-haiggoh.py")
        os.execv(sys.executable, [sys.executable, script] + argv)
    if not sys.stdin.isatty():
        print("get-haiggoh: the menu is interactive and needs a terminal. "
              "Try: get-haiggoh plan | apply | upgrade | shims   (or --help)", file=sys.stderr)
        return 2
    menu = os.environ.get("GET_HAIGGOH_MENU_SCRIPT") or os.path.join(HERE, "get-haiggoh-menu")
    os.execv(sys.executable, [sys.executable, menu])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

Then `chmod 755 bin/get-haiggoh`.

Only stdin is tested for a terminal, on purpose: the menu reads with `input()`, and the test captures stdout through a pipe, so a stdout check would wrongly refuse there.

- [ ] **Step 4: Run to verify pass**

Run: `~/.local/bin/pytest tests -q` — Expected: only the 1 pre-existing failure.

- [ ] **Step 5: Discriminant**

Commit, then change `sys.stdin.isatty()` to `True`-always (remove the guard): `test_bare_run_without_a_terminal_refuses_instead_of_crashing` must FAIL (menu runs, hits EOF, traceback). Restore via `git checkout -- bin/get-haiggoh`.

- [ ] **Step 6: Commit**

```bash
git add bin/get-haiggoh shortcuts tests/test_launcher.py
git commit -m "feat: get-haiggoh launcher (bare run opens the menu) and shortcuts declaration"
```

**🧪 Receipt 5:** pytest summary; `ls -l bin/get-haiggoh` showing mode `-rwxr-xr-x`; mutation failure and restored pass.

---

## Task 6: SessionStart hook adds non-colliding shims

**Files:**
- Modify: `hooks/check-installed.py` (restructure `main`, lines 88–137)
- Create: `tests/test_hook_shims.py`

**Behavior:** the hook creates (and silently refreshes) shims that collide with nothing. It never overwrites or prefixes. It runs even when the marketplace is unregistered or the daily refresh failed. One line is appended to the nudge for shims it just created. `GET_HAIGGOH_NO_SHIMS=1` disables it. The whole step is fail-safe (any exception → nothing).

- [ ] **Step 1: Write the failing tests** — create `tests/test_hook_shims.py`:

```python
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO_ROOT, "hooks", "check-installed.py")


def run_hook(world, extra_env=None):
    env = world.env()
    env.update(extra_env or {})
    return subprocess.run([sys.executable, HOOK], input="{}", capture_output=True, text=True,
                          env=env, timeout=20)


def test_hook_creates_missing_shims_even_when_marketplace_is_unregistered(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    r = run_hook(world)
    assert r.returncode == 0
    assert (world.bin / "waypoints").is_file()
    out = json.loads(r.stdout)
    assert "added PATH shortcuts: waypoints" in out["hookSpecificOutput"]["additionalContext"]


def test_hook_never_touches_a_collision(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    (world.bin / "waypoints").write_text("mine\n")
    r = run_hook(world)
    assert r.returncode == 0 and r.stdout.strip() == ""
    assert (world.bin / "waypoints").read_text() == "mine\n"
    assert not world.backups.exists()


def test_hook_is_silent_once_shims_exist(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    run_hook(world)
    r = run_hook(world)
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_no_shims_env_disables_the_hook_step(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    r = run_hook(world, {"GET_HAIGGOH_NO_SHIMS": "1"})
    assert r.returncode == 0 and r.stdout.strip() == ""
    assert list(world.bin.iterdir()) == []


def test_hook_survives_a_corrupt_installed_record(world):
    world.record.write_text("{not json")
    r = run_hook(world)
    assert r.returncode == 0 and r.stdout.strip() == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `~/.local/bin/pytest tests/test_hook_shims.py -q` — Expected: first test FAILS (no shim, empty stdout).

- [ ] **Step 3: Implement**

Read `hooks/check-installed.py` lines 88–137 again. Replace them (from `def main():` to the last line `sys.exit(0)`) with the block below. The original body becomes `_nudge_banner()`: every bare `return` becomes `return ""`, the `json.loads(sys.stdin...)` guard moves to the new `main`, and the final `print(...)` becomes `return banner`.

```python
def _add_missing_shims(installed):
    """Create PATH shims that collide with nothing. Never overwrites or prefixes: that is an
    explicit `get-haiggoh shims apply --on-collision=...`. Returns a one-line note naming the
    shortcuts just CREATED ('' if none). Fail-safe: any error -> ''."""
    if os.environ.get("GET_HAIGGOH_NO_SHIMS"):
        return ""
    try:
        import get_haiggoh_shims as s
        created = []
        for act in s.plan_shims(installed, policy="skip"):
            if act["action"] in ("create", "refresh"):
                s.apply_action(act)
                if act["action"] == "create":
                    created.append(act["name"])
        return ("get-haiggoh: added PATH shortcuts: " + ", ".join(created)) if created else ""
    except Exception:
        return ""


def _nudge_banner():
    known = c.load_json(c.known_marketplaces_path())
    marketplace_path = c.resolve_marketplace_json_path(known, "haiggoh")
    if not marketplace_path:
        return ""  # marketplace not registered on this machine -- nothing to check

    today = c.today()
    stamp_path = c.refresh_stamp_path()
    refreshing = c.should_refresh(stamp_path, today)
    if refreshing:
        if not _refresh_marketplace():
            return ""  # refresh failed/timed out -- do NOT diff against possibly-stale data

    marketplace_data = c.load_json(marketplace_path)
    catalog = c.load_marketplace_entries(marketplace_data)
    if not catalog:
        return ""

    installed = c.load_installed(c.load_json(c.installed_plugins_path()))

    # Option B: fetch remote versions at most once/day (on the refresh) and cache them
    # alongside the stamp; same-day boots reuse the cache so outdated nudges cost no network.
    if refreshing:
        remote_versions = _fetch_remote_versions(catalog, installed)
        c.save_refresh_state(stamp_path, today, remote_versions)  # date AND version cache
    else:
        remote_versions = c.load_cached_versions(stamp_path)

    skip_list = c.load_skip_list()
    missing = c.filter_missing_by_skip(c.compute_missing(catalog, installed, SELF_NAME), skip_list)
    outdated = c.filter_outdated_by_skip(
        c.compute_outdated(catalog, installed, remote_versions, SELF_NAME), skip_list)
    return c.format_nudge(missing, outdated)


def main():
    try:
        json.loads(sys.stdin.read() or "{}")
    except Exception:
        return  # malformed stdin -- fail-safe, no output

    # Shortcuts need only the local installed record, so they do not wait on the marketplace.
    shim_note = _add_missing_shims(c.load_installed(c.load_json(c.installed_plugins_path())))
    try:
        banner = _nudge_banner()
    except Exception:
        banner = ""
    banner = "\n".join(part for part in (banner, shim_note) if part)
    if banner:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                   "additionalContext": banner}}))


try:
    main()
except Exception:
    pass
sys.exit(0)
```

- [ ] **Step 4: Run to verify pass**

Run: `~/.local/bin/pytest tests -q` — Expected: only the pre-existing failure. The original hook tests (nudge for a missing plugin, malformed stdin, unregistered marketplace) must still pass, which proves the restructure kept the old behavior.

- [ ] **Step 5: Discriminant**

Commit, then change `policy="skip"` to `policy="overwrite"` in `_add_missing_shims`: `test_hook_never_touches_a_collision` must FAIL; restore via `git checkout -- hooks/check-installed.py`.

- [ ] **Step 6: Commit**

```bash
git add hooks/check-installed.py tests/test_hook_shims.py
git commit -m "feat(hook): add non-colliding PATH shortcuts at session start"
```

**🧪 Receipt 6:** pytest summary; the mutation failure and restored pass; output of running the hook against the fake world showing the JSON note.

---

## Task 7: Docs, version 0.8.0, dogfood from the branch

**Files:**
- Modify: `.claude-plugin/plugin.json`, `CHANGELOG.md`, `README.md`, plus every other file Phase 0 step 3.2 found that states `0.7.0`.

- [ ] **Step 1:** Bump `"version"` to `0.8.0` in `.claude-plugin/plugin.json`; add to `CHANGELOG.md` above `[0.7.0]`:

```markdown
## [0.8.0] — 2026-10-03

### Added
- PATH shortcuts: `get-haiggoh apply` (and the new `upgrade` alias) now puts every participating
  plugin's CLI on your shell PATH through version-independent shims in `~/.local/bin`.
  Plugins opt in with a `shortcuts` file at their root.
- `get-haiggoh shims [plan|apply] [--on-collision skip|overwrite|prefix]`.
- `get-haiggoh` command: no arguments opens the interactive menu; arguments go to the CLI.
- The SessionStart hook adds missing, non-colliding shortcuts and reports them.

### Safety
- Existing commands are never overwritten by default; `overwrite` backs the old link/file up to
  `~/.local/state/get-haiggoh/shim-backups/` first. `GET_HAIGGOH_NO_SHIMS=1` opts out.
```

- [ ] **Step 2:** Add a "PATH shortcuts" section to `README.md`: what a `shortcuts` file is, the three collision policies, how to undo an overwrite (`ln -sfn "$(cat ~/.local/state/get-haiggoh/shim-backups/<name>.<stamp>.link)" ~/.local/bin/<name>`), that `~/.local/bin` must be on PATH, and the env vars from `--help`.

- [ ] **Step 3: Dogfood from the branch, safely.** Run the real CLI against the real installed record but a TEMP shim dir, so nothing on the machine changes:

```bash
cd ~/ClaudeWorkspace/get-haiggoh-shortcuts
GET_HAIGGOH_SHIM_DIR="$(mktemp -d)" GET_HAIGGOH_SHIM_BACKUP_DIR="$(mktemp -d)" python3 bin/get-haiggoh.py shims plan --on-collision=overwrite
```
Expected: only `get-haiggoh` is listed (the only `shortcuts` file that exists in an installed plugin is this branch's, and the installed cache copy of get-haiggoh is 0.7.0 without one, so even that may be absent). State honestly which. This step proves the real `installed_plugins.json` parses; it is NOT proof that the four other plugins work (Task 8/9).

- [ ] **Step 4:** Full suite: `~/.local/bin/pytest tests -q` → only the pre-existing failure. Commit:

```bash
git add .claude-plugin/plugin.json CHANGELOG.md README.md
git commit -m "0.8.0: PATH shortcuts (docs, changelog, version)"
```

**🧪 Receipt 7:** `grep -rn "0\.7\.0"` over tracked files returns only historical CHANGELOG lines; dogfood output pasted; pytest summary.

---

## Task 8: `shortcuts` files in the four other plugin repos

`local:operator` candidate (see offload section). Repos: `waypoints` (command `waypoints`), `resume-interrupted` (`interrupted`), `lasting-plans` (`lasting-plans`), `cost-tracker` (`cost-tracker`). **Not free-agents.**

For EACH repo `R` with command `CMD` and new version `V` (table in Global Constraints):

- [ ] **Step 1: Check the source** — `git -C ~/ClaudeWorkspace/R status --porcelain` must be empty (it was on 2026-10-03). If not, stop and ask; do not touch the main checkout.
- [ ] **Step 2: Isolate** — `git -C ~/ClaudeWorkspace/R worktree add ../R-shortcut -b feature/path-shortcut`; work only in `~/ClaudeWorkspace/R-shortcut`.
- [ ] **Step 3: Discover the test command** — `ls tests` and the README; use the repo's own framework (pytest via `~/.local/bin/pytest` where the tests are Python). Do not introduce a new framework; if the tests are not Python, write the equivalent in the repo's style.
- [ ] **Step 4: Failing test** — add `tests/test_shortcuts_file.py` (adjust `CMD`):

```python
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_shortcuts_file_declares_real_executables():
    with open(os.path.join(ROOT, "shortcuts")) as f:
        names = [l.split("#")[0].strip() for l in f if l.split("#")[0].strip()]
    assert names == ["CMD"]
    for name in names:
        target = os.path.join(ROOT, "bin", name)
        assert os.path.isfile(target) and os.access(target, os.X_OK)
```
Run it; expect FAIL (`FileNotFoundError: shortcuts`).
- [ ] **Step 5: Create `shortcuts`** containing exactly:

```
# Commands this plugin puts on the user's shell PATH (read by get-haiggoh >= 0.8.0).
CMD
```
Rerun: PASS.
- [ ] **Step 6: Discriminant** — temporarily `mv bin/CMD bin/CMD.off`: the test must FAIL; `mv` it back; PASS.
- [ ] **Step 7: Version and notes** — bump to `V` in `.claude-plugin/plugin.json` (lasting-plans also has a top-level `VERSION` file: update it too); add a CHANGELOG entry ("Adds a `shortcuts` file so get-haiggoh can put `CMD` on your shell PATH"; resume-interrupted has an `[Unreleased]` section, so put it under the new version heading and keep any existing unreleased lines); add one README sentence. `grep` the old version to be sure nothing else states it.
- [ ] **Step 8: Full suite, then commit by path** — `shortcuts tests/test_shortcuts_file.py .claude-plugin/plugin.json CHANGELOG.md README.md` (+ `VERSION`). cost-tracker: do NOT edit `install.sh`; note in its CHANGELOG that the installer's own `~/.local/bin/cost-tracker` link and the get-haiggoh shim are alternatives, and that the shim wins once installed.

**🧪 Receipt 8 (per repo):** test command, FAIL-then-PASS output, the mutation failure, `git diff --stat`, `git log --oneline -1`, and `git -C ~/ClaudeWorkspace/R status --porcelain` (main checkout still clean).

---

## Task 9: Rollout on this machine — GATED

Requires the user's separate permission for each boundary. Nothing above pushes, merges, tags, or releases. Stop here and ask:

1. Push the five feature branches? (authority: separate permission)
2. Merge to each repo's default branch, tag, release? (an installer fetches the DEFAULT branch, so an unmerged branch is not obtainable). Merge order: the four plugin repos first, get-haiggoh last.
3. After release, refresh with `get-haiggoh apply` (plugin updates are version-gated: confirm the recorded versions actually moved; exit 0 with no copy is the known trap).
4. Show the dry run first: `get-haiggoh shims plan --on-collision=overwrite`. It should list `waypoints`, `interrupted`, `lasting-plans`, `cost-tracker` as `would OVERWRITE` (symlinks into `~/AntigravityWorkspace/antigravity-suite/packages/agy-*`) and `get-haiggoh` as `would create`. **Not** `csl` (free-agents is excluded). Get the user's confirmation, then `get-haiggoh shims apply --on-collision=overwrite`.
5. Dogfood by outcome, in the user's own terminal (`! waypoints`, `! get-haiggoh --help`, `! lasting-plans`, `! cost-tracker`, `! interrupted`): each must print the haiggoh plugin's output, and `ls -l ~/.local/bin/waypoints` must show a regular file containing `haiggoh-shim`, with a `.link` backup in `~/.local/state/get-haiggoh/shim-backups/`. Then simulate an update: confirm a shim still works after `claude plugin update` of one plugin.
6. Undo recipe, if the user wants the agy links back: `ln -sfn "$(cat ~/.local/state/get-haiggoh/shim-backups/<name>.<stamp>.link)" ~/.local/bin/<name>`.

**🧪 Receipt 9:** plan output, confirmation, apply output, the five outcome runs, backup listing. Anything not run is reported "not tested".

---

## Adversarial review

| Tempting shortcut | Plausible false success | Harm | Rule | Detecting receipt |
|---|---|---|---|---|
| Write the shim with `open(path, "w")` | Tests that only check "shim exists" pass | Writing through `~/.local/bin/waypoints` corrupts the agy package script | Temp file + `os.replace` | Task 3 `overwrite_replaces_the_link_without_writing_through_it` + mutation (a) |
| Resolve by `ls | sort | tail -1` | Works today | Picks the stale `get-haiggoh/1.0.0` directory; `1.9.0` beats `1.10.0` lexically | Record first, numeric fallback | Task 2 `record_wins…` and `fallback_picks_highest_numeric…` with mutations |
| Trust the `shortcuts` text as a path | Normal names work | `../../x` writes outside `~/.local/bin` | `valid_name` on every entry; `render_shim` re-validates | Task 1 invalid-name tests + mutation |
| Read the first line of every file in `~/.local/bin` | Fine on scripts | Hangs on the 71 MB `joyia` binary | Read 256 bytes | Task 3 `is_our_shim_reads_bytes_not_lines` |
| Run tests against the real `~/.local/bin` | Green | Real shims appear or get replaced | Autouse isolation fixture, `world` fixture | Every receipt shows the real dir untouched (`ls -l ~/.local/bin/waypoints` still an agy link until Task 9) |
| Hook returns early when the marketplace is unregistered | Old tests pass | Shortcuts never appear offline | Shim step runs before and independent of the nudge | Task 6 test 1 |
| Hook overwrites on a hunch | None visible | Silent replacement every session | Hook is `policy="skip"` only | Task 6 mutation |
| Count "71 passed" as a clean suite | One failure is hidden | Regression blamed on or masked by the pre-existing failure | Compare to the baseline line every time | Every receipt |
| Edit `cost-tracker/install.sh` to make the two mechanisms agree | Looks tidy | Out-of-scope change to a release artifact | Document only | Task 8 cost-tracker step |
| Touch free-agents to add `csl` | Would complete the feature | Collides with the user's in-flight merge | Prohibited | `git -C ~/ClaudeWorkspace/local-agents status` unchanged; no free-agents path in any `git diff --stat` |
| Push or merge "to test the install" | Installer sees the change | Crosses an unauthorized boundary | Dogfood from the branch with temp dirs (Task 7 step 3) | Authority matrix |

**Cannot be tested safely before rollout:** a real `claude plugin update` on the five plugins; behavior of the user's actual shell PATH ordering; the interactive menu beyond reaching it. These are covered in Task 9 under "not tested" until run.

## Final review and delivery

Answer aloud before reporting: What is implemented versus merely planned? Which receipts actually ran? Which tests are unrun? Is the pre-existing failing test reported as pre-existing? Is user work preserved (main checkouts untouched, free-agents untouched)? Did anything touch the real `~/.local/bin` before Task 9? Do `upgrade` and `apply` match, and does a bare `get-haiggoh` reach the menu? Did the work stop before push/merge/tag/release? Was this plan artifact re-read by placeholder scan (`grep -n "TBD\|TODO\|fill in" docs/superpowers/plans/2026-10-03-path-shortcuts.md`) before handoff?
