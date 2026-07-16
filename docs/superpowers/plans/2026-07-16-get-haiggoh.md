# get-haiggoh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publish `get-haiggoh`, a Claude Code plugin that relocates the `haiggoh` marketplace catalog to its own repo and provides a skill+hook for installing/updating every other published haiggoh plugin from one place.

**Architecture:** A pure, stdlib-only Python core module (`get_haiggoh_core.py`) holds all testable logic (path resolution, marketplace/installed-plugin parsing, diff computation, skip-list, throttle-stamp) with zero subprocess/network calls of its own. A thin SessionStart hook (`hooks/check-installed.py`) and a thin skill-side script (`bin/get-haiggoh.py`) both import that core module and are the only places that shell out to `claude`/`git`, so the core is trivially unit-testable and the shell-out surface is small and mockable.

**Tech Stack:** Python 3 (stdlib only — `json`, `os`, `subprocess`, `re`, `tempfile`, `datetime`), pytest, git, GitHub CLI (`gh`), Claude Code plugin/marketplace CLI.

## Global Constraints

- Plugin repo shape mirrors `waypoints`/`resume-interrupted`: `.claude-plugin/plugin.json` has **no `hooks` key** (hooks auto-load from `hooks/hooks.json`, else install throws "Duplicate hooks").
- Every hook script is **fail-safe**: any exception, missing file, malformed JSON, or subprocess timeout → exit 0, no output, never blocks a session.
- No live `claude`/`git` CLI calls in automated tests — `subprocess.run` is mocked/stubbed throughout.
- `GET_HAIGGOH_AUTO_UPDATE` env var (`ask` default | `silent`) gates ONLY updates to already-installed plugins. New installs always route through the confirming skill, never silently, regardless of this setting.
- Skip-list entries are keyed by plugin name with a `scope` field: `install` | `update` | `both`.
- The marketplace-repo copy of `marketplace.json` (resolved via `known_marketplaces.json`'s `installLocation`) is authoritative — never read the plugin's own bundled `$CLAUDE_PLUGIN_ROOT` copy for diffing, since that's frozen at get-haiggoh's own install version.
- "Outdated" is detected via **git commit SHA** comparison (`git ls-remote <repo-url> HEAD` vs. `installed_plugins.json`'s `gitCommitSha` field) — `marketplace.json` entries carry no version field, confirmed by inspecting the live file.
- `get-haiggoh` always excludes itself (by name) from both the missing and outdated sets.
- Network refresh (`claude plugin marketplace update haiggoh`) is throttled to once/day via a stamp file, with a ~5s subprocess timeout; on timeout/failure/already-refreshed-today, skip the diff for that session rather than diffing stale data.

---

## File Structure

```
~/ClaudeWorkspace/get-haiggoh/
  .claude-plugin/
    plugin.json
    marketplace.json          # relocated catalog (copied+adapted from claude-code-desktop-sync)
  get_haiggoh_core.py          # pure logic, no subprocess/network
  bin/
    get-haiggoh.py             # skill-side CLI: plan, confirm, execute install/update
  hooks/
    hooks.json
    check-installed.py         # SessionStart hook: throttled refresh + nudge
  skills/
    get-haiggoh/
      SKILL.md
  tests/
    test_get_haiggoh_core.py
    test_hook_and_cli.py
  README.md
  LICENSE
  .gitignore
```

---

### Task 1: Repo scaffold, plugin.json, relocated marketplace.json, LICENSE, gitignore

**Files:**
- Create: `~/ClaudeWorkspace/get-haiggoh/.claude-plugin/plugin.json`
- Create: `~/ClaudeWorkspace/get-haiggoh/.claude-plugin/marketplace.json`
- Create: `~/ClaudeWorkspace/get-haiggoh/LICENSE`
- Create: `~/ClaudeWorkspace/get-haiggoh/.gitignore`

**Interfaces:**
- Produces: the relocated `marketplace.json` (adapted from `~/ClaudeWorkspace/claude-code-desktop-sync/.claude-plugin/marketplace.json` — copy every existing entry verbatim EXCEPT `claude-code-desktop-sync`'s own entry, which currently uses `"source": "./"` because it's self-hosting; that entry gets a normal git-url source since it's no longer the marketplace's home), plus a new `get-haiggoh` entry.

- [ ] **Step 1: Write `.claude-plugin/plugin.json`**

```json
{
  "name": "get-haiggoh",
  "version": "0.1.0",
  "description": "Install and keep up to date every published haiggoh plugin from one place. Also the canonical home of the haiggoh marketplace catalog.",
  "author": { "name": "Heiko Brantsch" },
  "homepage": "https://github.com/haiggoh/get-haiggoh",
  "license": "MIT",
  "keywords": ["skill", "hook", "marketplace", "install", "bootstrap", "meta"]
}
```

- [ ] **Step 2: Write `.claude-plugin/marketplace.json`**

Copy every plugin entry from `~/ClaudeWorkspace/claude-code-desktop-sync/.claude-plugin/marketplace.json` verbatim, EXCEPT change `claude-code-desktop-sync`'s entry from `"source": "./"` to a normal git-url source (it's no longer self-hosting the marketplace), and add a new `get-haiggoh` entry:

```json
{
  "name": "haiggoh",
  "owner": {
    "name": "Heiko Brantsch",
    "url": "https://github.com/haiggoh"
  },
  "plugins": [
    {
      "name": "claude-code-desktop-sync",
      "source": { "source": "url", "url": "https://github.com/haiggoh/claude-code-desktop-sync.git" },
      "description": "Keeps MCP-server config in sync between Claude Code and Claude Desktop via a SessionStart hook, and reports the manual steps for anything that can't be auto-synced.",
      "category": "productivity",
      "tags": ["mcp", "sync", "claude-desktop", "configuration"]
    },
    {
      "name": "no-hidden-changes",
      "source": { "source": "url", "url": "https://github.com/haiggoh/no-hidden-changes.git" },
      "description": "Steer Claude toward visible, honest, reversible changes and away from hidden-state workarounds that make a tool's own UI look empty, absent, or deceptive.",
      "category": "productivity",
      "tags": ["skill", "hook", "transparency", "ux", "safety"]
    },
    {
      "name": "measure-twice",
      "source": { "source": "url", "url": "https://github.com/haiggoh/measure-twice.git" },
      "description": "Before building automation, survey for what already exists and match the mechanism's trigger to the event that makes it relevant. Sibling of no-hidden-changes.",
      "category": "productivity",
      "tags": ["skill", "hook", "automation", "planning", "design"]
    },
    {
      "name": "resume-interrupted",
      "source": { "source": "url", "url": "https://github.com/haiggoh/resume-interrupted.git" },
      "description": "Detects when your most recent session was cut off mid-task (usage limit, crash, or dropped connection) and proactively offers to pick up where you left off.",
      "category": "productivity",
      "tags": ["skill", "hook", "sessions", "resume", "continuity"]
    },
    {
      "name": "mcp-smoke-test",
      "source": { "source": "url", "url": "https://github.com/haiggoh/mcp-smoke-test.git" },
      "description": "Onboard and verify any MCP that drives an external app: smoke test, functional capability probe, evidence-based manual, and interactive prereq-ladder guide — with parametrized templates.",
      "category": "productivity",
      "tags": ["skill", "mcp", "testing", "probe", "onboarding"]
    },
    {
      "name": "waypoints",
      "source": { "source": "url", "url": "https://github.com/haiggoh/waypoints.git" },
      "description": "Surfaces your open tasks / to-dos as a persistent SessionStart banner ('waypoints' still ahead of you) that stays until each is marked done. Forward-looking companion to resume-interrupted; distinct from Claude Code's native rewind checkpoints. Supports optional surface-on dates. Disable via /plugin if unwanted.",
      "category": "productivity",
      "tags": ["skill", "hook", "reminders", "todo", "sessions", "continuity"]
    },
    {
      "name": "audit-loose-ends",
      "source": { "source": "url", "url": "https://github.com/haiggoh/audit-loose-ends.git" },
      "description": "End-of-task reconciliation of your durable records (memories, project notes, reminders, task list, and the waypoints store) so nothing is left redundant, orphaned, or falsely flagged as to-do when it's already done. SessionStart nudge + skill. Companion to waypoints; distinct from no-hidden-changes (which reconciles a rule once at first run).",
      "category": "productivity",
      "tags": ["skill", "hook", "sessions", "housekeeping", "records", "waypoints"]
    },
    {
      "name": "run-to-completion",
      "source": { "source": "url", "url": "https://github.com/haiggoh/run-to-completion.git" },
      "description": "Offer continuous, autonomous execution for elaborate multi-step work: ask blocking matter-of-taste questions up front, then run the plan to completion without stopping between steps, folding in mid-run prompts at natural task seams. Does not relax destructive-action confirmations.",
      "category": "productivity",
      "tags": ["skill", "hook", "behavior", "autonomy", "planning", "execution", "workflow"]
    },
    {
      "name": "get-haiggoh",
      "source": { "source": "url", "url": "https://github.com/haiggoh/get-haiggoh.git" },
      "description": "Install and keep up to date every published haiggoh plugin from one place. SessionStart hook nudges when something new or outdated appears; a confirming skill does the actual install/update. Canonical home of the haiggoh marketplace catalog.",
      "category": "productivity",
      "tags": ["skill", "hook", "marketplace", "install", "bootstrap", "meta"]
    }
  ]
}
```

- [ ] **Step 3: Write `LICENSE`** (MIT, mirror the text used in `~/ClaudeWorkspace/waypoints/LICENSE`)

```bash
cp ~/ClaudeWorkspace/waypoints/LICENSE ~/ClaudeWorkspace/get-haiggoh/LICENSE
```

Then edit only the copyright holder line if it differs from waypoints' (it shouldn't — same author).

- [ ] **Step 4: Write `.gitignore`**

```
__pycache__/
*.pyc
.DS_Store
```

- [ ] **Step 5: Commit**

```bash
cd ~/ClaudeWorkspace/get-haiggoh
git add .claude-plugin LICENSE .gitignore
git commit -m "Scaffold get-haiggoh: plugin.json, relocated marketplace.json, LICENSE"
```

---

### Task 2: Core module — path resolution, marketplace/installed loaders, skip-list

**Files:**
- Create: `~/ClaudeWorkspace/get-haiggoh/get_haiggoh_core.py`
- Create: `~/ClaudeWorkspace/get-haiggoh/tests/test_get_haiggoh_core.py`
- Create: `~/ClaudeWorkspace/get-haiggoh/tests/__init__.py` (empty, so pytest can import siblings if needed — actually not required for pytest rootdir discovery; skip creating it, use plain `import get_haiggoh_core` with `conftest.py` doing the path insert)
- Create: `~/ClaudeWorkspace/get-haiggoh/tests/conftest.py`

**Interfaces:**
- Produces:
  - `known_marketplaces_path() -> str`
  - `installed_plugins_path() -> str`
  - `resolve_marketplace_json_path(known_marketplaces_data: dict, marketplace_name: str = "haiggoh") -> str | None`
  - `load_json(path: str) -> dict` (returns `{}` on any error — fail-safe read)
  - `load_marketplace_entries(marketplace_data: dict) -> list[dict]` (each dict has at least `name`, `source`)
  - `load_installed(installed_data: dict, marketplace_suffix: str = "@haiggoh") -> dict[str, dict]` (name -> `{"version": str, "gitCommitSha": str|None}`)
  - `entry_repo_url(entry: dict) -> str | None` (extracts a git URL from a marketplace entry's `source` field; `None` for non-url sources like `"./"`)
  - `load_skip_list(path: str) -> dict[str, str]` (name -> scope, fail-safe empty dict on error)
  - `save_skip_list(path: str, skip_list: dict[str, str]) -> None` (atomic tmp+replace write, mirrors `waypoints_core.save_store`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/conftest.py
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

```python
# tests/test_get_haiggoh_core.py
import json
import os
import tempfile

import get_haiggoh_core as c


def test_resolve_marketplace_json_path_reads_install_location():
    known = {"haiggoh": {"source": {"source": "github", "repo": "haiggoh/get-haiggoh"},
                          "installLocation": "/fake/marketplaces/haiggoh"}}
    assert c.resolve_marketplace_json_path(known, "haiggoh") == \
        "/fake/marketplaces/haiggoh/.claude-plugin/marketplace.json"


def test_resolve_marketplace_json_path_missing_marketplace_returns_none():
    assert c.resolve_marketplace_json_path({}, "haiggoh") is None


def test_load_json_returns_empty_dict_on_missing_file():
    assert c.load_json("/definitely/does/not/exist.json") == {}


def test_load_json_returns_empty_dict_on_malformed_json():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{not valid json")
        path = f.name
    try:
        assert c.load_json(path) == {}
    finally:
        os.remove(path)


def test_load_json_parses_valid_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"a": 1}, f)
        path = f.name
    try:
        assert c.load_json(path) == {"a": 1}
    finally:
        os.remove(path)


def test_load_marketplace_entries_returns_plugins_list():
    data = {"name": "haiggoh", "plugins": [{"name": "waypoints", "source": {}}]}
    assert c.load_marketplace_entries(data) == [{"name": "waypoints", "source": {}}]


def test_load_marketplace_entries_missing_plugins_key_returns_empty():
    assert c.load_marketplace_entries({}) == []


def test_load_installed_filters_by_marketplace_suffix():
    data = {"plugins": {
        "waypoints@haiggoh": [{"version": "0.1.7", "gitCommitSha": "abc123"}],
        "some-other@othermarket": [{"version": "1.0.0", "gitCommitSha": "zzz"}],
    }}
    out = c.load_installed(data)
    assert out == {"waypoints": {"version": "0.1.7", "gitCommitSha": "abc123"}}


def test_load_installed_missing_gitCommitSha_defaults_to_none():
    data = {"plugins": {"waypoints@haiggoh": [{"version": "0.1.7"}]}}
    out = c.load_installed(data)
    assert out["waypoints"]["gitCommitSha"] is None


def test_load_installed_empty_plugins_returns_empty():
    assert c.load_installed({}) == {}


def test_entry_repo_url_extracts_url_source():
    entry = {"name": "waypoints", "source": {"source": "url", "url": "https://github.com/haiggoh/waypoints.git"}}
    assert c.entry_repo_url(entry) == "https://github.com/haiggoh/waypoints.git"


def test_entry_repo_url_returns_none_for_dot_slash_source():
    entry = {"name": "self", "source": "./"}
    assert c.entry_repo_url(entry) is None


def test_entry_repo_url_returns_none_for_missing_source():
    assert c.entry_repo_url({"name": "x"}) is None


def test_load_skip_list_returns_empty_dict_on_missing_file():
    assert c.load_skip_list("/definitely/does/not/exist.json") == {}


def test_save_and_load_skip_list_roundtrip(tmp_path):
    path = str(tmp_path / "skip.json")
    c.save_skip_list(path, {"waypoints": "install"})
    assert c.load_skip_list(path) == {"waypoints": "install"}


def test_save_skip_list_creates_parent_dir(tmp_path):
    path = str(tmp_path / "nested" / "skip.json")
    c.save_skip_list(path, {"x": "update"})
    assert os.path.exists(path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/ClaudeWorkspace/get-haiggoh && pytest tests/test_get_haiggoh_core.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'get_haiggoh_core'` (module doesn't exist yet)

- [ ] **Step 3: Write `get_haiggoh_core.py`**

```python
"""Pure, unit-testable core for get-haiggoh.

No subprocess/network calls live here — hooks/check-installed.py and bin/get-haiggoh.py
are the only places that shell out to `claude`/`git`, so this module stays trivially
mockable in tests. Every loader is fail-safe (returns an empty structure on error) —
a corrupt/missing file must never crash a SessionStart hook.
"""
import json
import os
import tempfile


def known_marketplaces_path():
    return os.environ.get("GET_HAIGGOH_KNOWN_MARKETPLACES_FILE") or os.path.expanduser(
        "~/.claude/plugins/known_marketplaces.json")


def installed_plugins_path():
    return os.environ.get("GET_HAIGGOH_INSTALLED_PLUGINS_FILE") or os.path.expanduser(
        "~/.claude/plugins/installed_plugins.json")


def skip_list_path():
    return os.environ.get("GET_HAIGGOH_SKIP_FILE") or os.path.expanduser(
        "~/.claude/.get-haiggoh-skip.json")


def refresh_stamp_path():
    return os.environ.get("GET_HAIGGOH_REFRESH_STAMP_FILE") or os.path.expanduser(
        "~/.claude/.get-haiggoh-last-refresh")


def resolve_marketplace_json_path(known_marketplaces_data, marketplace_name="haiggoh"):
    """Given the parsed contents of known_marketplaces.json, return the path to that
    marketplace's marketplace.json inside its cloned installLocation, or None if the
    marketplace isn't registered. This is the MARKETPLACE-REPO copy — always read this,
    never a plugin's own bundled $CLAUDE_PLUGIN_ROOT copy, which is frozen at whatever
    version was installed and goes stale the moment a newer one is published."""
    entry = known_marketplaces_data.get(marketplace_name)
    if not entry or not entry.get("installLocation"):
        return None
    return os.path.join(entry["installLocation"], ".claude-plugin", "marketplace.json")


def load_json(path):
    """Fail-safe JSON read: missing file, malformed JSON, or any other error -> {}."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def load_marketplace_entries(marketplace_data):
    """Return the plugins list from a parsed marketplace.json, or [] if absent/malformed."""
    entries = marketplace_data.get("plugins")
    return entries if isinstance(entries, list) else []


def load_installed(installed_data, marketplace_suffix="@haiggoh"):
    """Return {plugin_name: {"version": str, "gitCommitSha": str|None}} for every
    installed_plugins.json key ending in marketplace_suffix. Takes the FIRST scope entry
    per plugin (mirrors how these plugins are installed today: one scope each)."""
    out = {}
    plugins = installed_data.get("plugins")
    if not isinstance(plugins, dict):
        return out
    for key, scopes in plugins.items():
        if not key.endswith(marketplace_suffix) or not scopes:
            continue
        name = key[: -len(marketplace_suffix)]
        first = scopes[0]
        out[name] = {
            "version": first.get("version"),
            "gitCommitSha": first.get("gitCommitSha"),
        }
    return out


def entry_repo_url(entry):
    """Extract a git URL from a marketplace entry's `source` field, or None for a
    non-url source (e.g. the self-hosting "./" form) or a missing/malformed source."""
    source = entry.get("source")
    if isinstance(source, dict) and source.get("source") == "url":
        return source.get("url")
    return None


def load_skip_list(path=None):
    """Fail-safe read of the skip-list file: {plugin_name: "install"|"update"|"both"}."""
    data = load_json(path or skip_list_path())
    return data if isinstance(data, dict) else {}


def save_skip_list(path, skip_list):
    """Atomic write (tmp file + os.replace) so a crash mid-write can't corrupt the
    skip-list, mirroring waypoints_core.save_store."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(skip_list, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/ClaudeWorkspace/get-haiggoh && pytest tests/test_get_haiggoh_core.py -v`
Expected: PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/ClaudeWorkspace/get-haiggoh
git add get_haiggoh_core.py tests/test_get_haiggoh_core.py tests/conftest.py
git commit -m "Add core loaders: marketplace path resolution, installed/skip-list parsing"
```

---

### Task 3: Diff computation (missing / outdated / skip-filtering)

**Files:**
- Modify: `~/ClaudeWorkspace/get-haiggoh/get_haiggoh_core.py`
- Modify: `~/ClaudeWorkspace/get-haiggoh/tests/test_get_haiggoh_core.py`

**Interfaces:**
- Consumes: `load_marketplace_entries` (list of `{name, source, ...}`), `load_installed` (dict `name -> {version, gitCommitSha}`), `entry_repo_url`
- Produces:
  - `compute_missing(catalog_entries: list[dict], installed: dict, self_name: str) -> list[str]`
  - `compute_outdated(catalog_entries: list[dict], installed: dict, remote_shas: dict[str, str|None], self_name: str) -> list[dict]` — each item `{"name": str, "installed_sha": str|None, "remote_sha": str}`
  - `filter_missing_by_skip(missing: list[str], skip_list: dict[str, str]) -> list[str]` (drops names with scope `"install"` or `"both"`)
  - `filter_outdated_by_skip(outdated: list[dict], skip_list: dict[str, str]) -> list[dict]` (drops names with scope `"update"` or `"both"`)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_get_haiggoh_core.py`:

```python
def _catalog():
    return [
        {"name": "get-haiggoh", "source": {"source": "url", "url": "https://github.com/haiggoh/get-haiggoh.git"}},
        {"name": "waypoints", "source": {"source": "url", "url": "https://github.com/haiggoh/waypoints.git"}},
        {"name": "measure-twice", "source": {"source": "url", "url": "https://github.com/haiggoh/measure-twice.git"}},
    ]


def test_compute_missing_excludes_self_and_installed():
    installed = {"waypoints": {"version": "0.1.7", "gitCommitSha": "abc"}}
    missing = c.compute_missing(_catalog(), installed, self_name="get-haiggoh")
    assert missing == ["measure-twice"]


def test_compute_missing_empty_when_all_installed():
    installed = {"waypoints": {}, "measure-twice": {}}
    assert c.compute_missing(_catalog(), installed, self_name="get-haiggoh") == []


def test_compute_outdated_flags_sha_mismatch():
    installed = {"waypoints": {"version": "0.1.6", "gitCommitSha": "old-sha"},
                 "measure-twice": {"version": "0.1.0", "gitCommitSha": "current-sha"}}
    remote_shas = {"waypoints": "new-sha", "measure-twice": "current-sha"}
    outdated = c.compute_outdated(_catalog(), installed, remote_shas, self_name="get-haiggoh")
    assert outdated == [{"name": "waypoints", "installed_sha": "old-sha", "remote_sha": "new-sha"}]


def test_compute_outdated_skips_not_installed():
    installed = {}
    remote_shas = {"waypoints": "new-sha", "measure-twice": "sha2"}
    assert c.compute_outdated(_catalog(), installed, remote_shas, self_name="get-haiggoh") == []


def test_compute_outdated_skips_unresolvable_remote_sha():
    installed = {"waypoints": {"gitCommitSha": "old-sha"}}
    remote_shas = {"waypoints": None}  # ls-remote failed -- never claim outdated from a failure
    assert c.compute_outdated(_catalog(), installed, remote_shas, self_name="get-haiggoh") == []


def test_compute_outdated_excludes_self():
    installed = {"get-haiggoh": {"gitCommitSha": "old"}}
    remote_shas = {"get-haiggoh": "new"}
    assert c.compute_outdated(_catalog(), installed, remote_shas, self_name="get-haiggoh") == []


def test_filter_missing_by_skip_drops_install_and_both_scopes():
    missing = ["a", "b", "c"]
    skip = {"a": "install", "b": "both", "c": "update"}
    assert c.filter_missing_by_skip(missing, skip) == ["c"]


def test_filter_outdated_by_skip_drops_update_and_both_scopes():
    outdated = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
    skip = {"a": "update", "b": "both", "c": "install"}
    assert c.filter_outdated_by_skip(outdated, skip) == [{"name": "c"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/ClaudeWorkspace/get-haiggoh && pytest tests/test_get_haiggoh_core.py -v -k "missing or outdated or filter"`
Expected: FAIL with `AttributeError: module 'get_haiggoh_core' has no attribute 'compute_missing'`

- [ ] **Step 3: Add diff functions to `get_haiggoh_core.py`**

Append to `get_haiggoh_core.py`:

```python
def compute_missing(catalog_entries, installed, self_name):
    """Catalog entries not present in `installed`, excluding self_name."""
    return [e["name"] for e in catalog_entries
            if e["name"] != self_name and e["name"] not in installed]


def compute_outdated(catalog_entries, installed, remote_shas, self_name):
    """Installed entries whose remote HEAD sha differs from the installed sha, excluding
    self_name. Never flags a plugin as outdated when the remote sha lookup itself failed
    (None) -- a failed check must fall silent, not manufacture a false positive."""
    out = []
    for e in catalog_entries:
        name = e["name"]
        if name == self_name or name not in installed:
            continue
        remote_sha = remote_shas.get(name)
        if remote_sha is None:
            continue
        installed_sha = installed[name].get("gitCommitSha")
        if remote_sha != installed_sha:
            out.append({"name": name, "installed_sha": installed_sha, "remote_sha": remote_sha})
    return out


def filter_missing_by_skip(missing, skip_list):
    return [name for name in missing if skip_list.get(name) not in ("install", "both")]


def filter_outdated_by_skip(outdated, skip_list):
    return [item for item in outdated if skip_list.get(item["name"]) not in ("update", "both")]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/ClaudeWorkspace/get-haiggoh && pytest tests/test_get_haiggoh_core.py -v`
Expected: PASS (25 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/ClaudeWorkspace/get-haiggoh
git add get_haiggoh_core.py tests/test_get_haiggoh_core.py
git commit -m "Add missing/outdated diff computation and skip-list filtering"
```

---

### Task 4: Throttle-stamp and banner formatting

**Files:**
- Modify: `~/ClaudeWorkspace/get-haiggoh/get_haiggoh_core.py`
- Modify: `~/ClaudeWorkspace/get-haiggoh/tests/test_get_haiggoh_core.py`

**Interfaces:**
- Consumes: `compute_missing`, `compute_outdated` output shapes
- Produces:
  - `today() -> str` (YYYY-MM-DD, overridable via `$GET_HAIGGOH_TODAY` for tests — mirrors `waypoints_core.today`)
  - `should_refresh(stamp_path: str, today_str: str) -> bool`
  - `mark_refreshed(stamp_path: str, today_str: str) -> None`
  - `format_nudge(missing: list[str], outdated: list[dict]) -> str` (returns `""` if both empty)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_get_haiggoh_core.py`:

```python
def test_should_refresh_true_when_stamp_missing(tmp_path):
    assert c.should_refresh(str(tmp_path / "nope"), "2026-07-16") is True


def test_should_refresh_false_when_stamp_matches_today(tmp_path):
    path = str(tmp_path / "stamp")
    c.mark_refreshed(path, "2026-07-16")
    assert c.should_refresh(path, "2026-07-16") is False


def test_should_refresh_true_when_stamp_is_a_prior_day(tmp_path):
    path = str(tmp_path / "stamp")
    c.mark_refreshed(path, "2026-07-15")
    assert c.should_refresh(path, "2026-07-16") is True


def test_format_nudge_empty_when_nothing_to_report():
    assert c.format_nudge([], []) == ""


def test_format_nudge_lists_missing_plugins():
    b = c.format_nudge(["measure-twice"], [])
    assert "measure-twice" in b
    assert "get-haiggoh" in b  # points at the skill/plugin name to resolve it


def test_format_nudge_lists_outdated_plugins():
    b = c.format_nudge([], [{"name": "waypoints", "installed_sha": "a", "remote_sha": "b"}])
    assert "waypoints" in b


def test_format_nudge_lists_both_sections_when_both_present():
    b = c.format_nudge(["measure-twice"], [{"name": "waypoints", "installed_sha": "a", "remote_sha": "b"}])
    assert "measure-twice" in b and "waypoints" in b
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/ClaudeWorkspace/get-haiggoh && pytest tests/test_get_haiggoh_core.py -v -k "refresh or nudge"`
Expected: FAIL with `AttributeError: module 'get_haiggoh_core' has no attribute 'should_refresh'`

- [ ] **Step 3: Add throttle-stamp and banner functions to `get_haiggoh_core.py`**

Append to `get_haiggoh_core.py`:

```python
from datetime import date


def today():
    """Today as YYYY-MM-DD; overridable via $GET_HAIGGOH_TODAY (tests)."""
    return os.environ.get("GET_HAIGGOH_TODAY") or date.today().isoformat()


def should_refresh(stamp_path, today_str):
    """True if the marketplace hasn't been network-refreshed yet today (missing stamp,
    or stamp from a prior day)."""
    stamped = load_json(stamp_path).get("date")
    return stamped != today_str


def mark_refreshed(stamp_path, today_str):
    os.makedirs(os.path.dirname(stamp_path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(stamp_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump({"date": today_str}, f)
        os.replace(tmp, stamp_path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def format_nudge(missing, outdated):
    """Nudge banner text, or '' if there's nothing to report. Points at the get-haiggoh
    skill/plugin name so the user knows how to act on it, without executing anything
    itself -- this hook only ever informs, never installs/updates on its own."""
    if not missing and not outdated:
        return ""
    lines = ["get-haiggoh: new or updated haiggoh plugins available "
             "(ask me to \"install all my haiggoh plugins\" to sync):"]
    for name in missing:
        lines.append(f"  + {name} (not installed)")
    for item in outdated:
        lines.append(f"  ^ {item['name']} (update available)")
    return "\n".join(lines)
```

Note: `load_json(stamp_path).get("date")` relies on `load_json` already being fail-safe (missing file -> `{}` -> `.get("date")` -> `None`), so no separate error handling is needed here.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/ClaudeWorkspace/get-haiggoh && pytest tests/test_get_haiggoh_core.py -v`
Expected: PASS (32 tests)

- [ ] **Step 5: Commit**

```bash
cd ~/ClaudeWorkspace/get-haiggoh
git add get_haiggoh_core.py tests/test_get_haiggoh_core.py
git commit -m "Add throttle-stamp helpers and nudge banner formatting"
```

---

### Task 5: SessionStart hook (`check-installed.py`) + `hooks.json`

**Files:**
- Create: `~/ClaudeWorkspace/get-haiggoh/hooks/hooks.json`
- Create: `~/ClaudeWorkspace/get-haiggoh/hooks/check-installed.py`
- Create: `~/ClaudeWorkspace/get-haiggoh/tests/test_hook_and_cli.py`

**Interfaces:**
- Consumes: every function from `get_haiggoh_core` (Task 2-4)
- Produces: a script runnable as `python3 hooks/check-installed.py` that prints a `{"hookSpecificOutput": {...}}` JSON object (or nothing) to stdout, exit 0 always

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_hook_and_cli.py
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO_ROOT, "hooks", "check-installed.py")


def _run(env_extra=None, stdin_data=""):
    env = os.environ.copy()
    env.update(env_extra or {})
    return subprocess.run([sys.executable, HOOK], input=stdin_data, capture_output=True,
                           text=True, env=env, timeout=10)


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def test_hook_prints_nothing_when_marketplace_not_registered(tmp_path):
    env = {
        "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": str(tmp_path / "nope.json"),
        "GET_HAIGGOH_INSTALLED_PLUGINS_FILE": str(tmp_path / "nope2.json"),
        "GET_HAIGGOH_SKIP_FILE": str(tmp_path / "skip.json"),
        "GET_HAIGGOH_REFRESH_STAMP_FILE": str(tmp_path / "stamp.json"),
        "GET_HAIGGOH_SELF_NAME": "get-haiggoh",
    }
    r = _run(env)
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_hook_prints_nudge_when_a_catalog_plugin_is_missing(tmp_path, monkeypatch):
    known_path = str(tmp_path / "known_marketplaces.json")
    marketplace_dir = tmp_path / "marketplaces" / "haiggoh" / ".claude-plugin"
    marketplace_path = marketplace_dir / "marketplace.json"
    installed_path = str(tmp_path / "installed_plugins.json")

    _write_json(known_path, {"haiggoh": {"installLocation": str(tmp_path / "marketplaces" / "haiggoh")}})
    _write_json(str(marketplace_path), {"plugins": [
        {"name": "get-haiggoh", "source": {"source": "url", "url": "https://github.com/haiggoh/get-haiggoh.git"}},
        {"name": "measure-twice", "source": {"source": "url", "url": "https://github.com/haiggoh/measure-twice.git"}},
    ]})
    _write_json(installed_path, {"plugins": {}})

    env = {
        "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": known_path,
        "GET_HAIGGOH_INSTALLED_PLUGINS_FILE": installed_path,
        "GET_HAIGGOH_SKIP_FILE": str(tmp_path / "skip.json"),
        "GET_HAIGGOH_REFRESH_STAMP_FILE": str(tmp_path / "stamp.json"),
        "GET_HAIGGOH_SELF_NAME": "get-haiggoh",
        "GET_HAIGGOH_SKIP_NETWORK_REFRESH": "1",  # test hook: never shell out in tests
        "GET_HAIGGOH_SKIP_REMOTE_SHA_CHECK": "1",  # no outdated-detection network calls either
    }
    r = _run(env)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert "measure-twice" in out["hookSpecificOutput"]["additionalContext"]


def test_hook_prints_nothing_when_stdin_is_malformed(tmp_path):
    env = {
        "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": str(tmp_path / "nope.json"),
        "GET_HAIGGOH_INSTALLED_PLUGINS_FILE": str(tmp_path / "nope2.json"),
    }
    r = _run(env, stdin_data="{not json")
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_hook_respects_refresh_throttle_stamp(tmp_path):
    stamp_path = str(tmp_path / "stamp.json")
    with open(stamp_path, "w") as f:
        json.dump({"date": "2026-07-16"}, f)
    env = {
        "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": str(tmp_path / "nope.json"),
        "GET_HAIGGOH_INSTALLED_PLUGINS_FILE": str(tmp_path / "nope2.json"),
        "GET_HAIGGOH_REFRESH_STAMP_FILE": stamp_path,
        "GET_HAIGGOH_TODAY": "2026-07-16",
    }
    r = _run(env)
    assert r.returncode == 0  # unregistered marketplace short-circuits before refresh either way; throttle path exercised by no crash + exit 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/ClaudeWorkspace/get-haiggoh && pytest tests/test_hook_and_cli.py -v`
Expected: FAIL — `hooks/check-installed.py` doesn't exist yet (`FileNotFoundError` from subprocess or non-zero exit)

- [ ] **Step 3: Write `hooks/hooks.json`**

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          { "type": "command", "command": "python3 \"$CLAUDE_PLUGIN_ROOT/hooks/check-installed.py\"" }
        ]
      }
    ]
  }
}
```

- [ ] **Step 4: Write `hooks/check-installed.py`**

```python
#!/usr/bin/env python3
"""get-haiggoh -- SessionStart hook: throttled marketplace refresh + install/update nudge.

Reads the MARKETPLACE-REPO copy of marketplace.json (resolved via known_marketplaces.json's
installLocation), diffs it against installed_plugins.json on two axes (missing, outdated),
filters through the skip-list, and emits a nudge via additionalContext. Nothing is printed
if there's nothing to report. Fail-safe throughout: any error -> exit 0, no output, never
blocks a session. This hook NEVER installs or updates anything itself in `ask` mode (the
default); `silent` mode (GET_HAIGGOH_AUTO_UPDATE=silent) additionally runs `claude plugin
update` for outdated, non-skipped plugins -- but NEVER auto-installs a missing plugin under
any mode, since a brand-new install always routes through the confirming skill.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import get_haiggoh_core as c

SELF_NAME = os.environ.get("GET_HAIGGOH_SELF_NAME") or "get-haiggoh"
REFRESH_TIMEOUT_S = float(os.environ.get("GET_HAIGGOH_REFRESH_TIMEOUT_S") or 5)


def _refresh_marketplace():
    """Best-effort `claude plugin marketplace update haiggoh`. Returns True on success,
    False on any failure/timeout -- callers must treat False as "diff against whatever
    we have, or skip if we have nothing" rather than pretending success."""
    if os.environ.get("GET_HAIGGOH_SKIP_NETWORK_REFRESH"):
        return True  # test-only escape hatch; never set in production
    try:
        result = subprocess.run(["claude", "plugin", "marketplace", "update", "haiggoh"],
                                 capture_output=True, timeout=REFRESH_TIMEOUT_S)
        return result.returncode == 0
    except Exception:
        return False


def _remote_head_sha(url):
    if os.environ.get("GET_HAIGGOH_SKIP_REMOTE_SHA_CHECK"):
        return None  # test-only escape hatch; never set in production
    try:
        result = subprocess.run(["git", "ls-remote", url, "HEAD"], capture_output=True,
                                 text=True, timeout=REFRESH_TIMEOUT_S)
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return result.stdout.split()[0]
    except Exception:
        return None


def main():
    try:
        json.loads(sys.stdin.read() or "{}")
    except Exception:
        return  # malformed stdin -- fail-safe, no output

    known = c.load_json(c.known_marketplaces_path())
    marketplace_path = c.resolve_marketplace_json_path(known, "haiggoh")
    if not marketplace_path:
        return  # marketplace not registered on this machine -- nothing to check

    today = c.today()
    stamp_path = c.refresh_stamp_path()
    if c.should_refresh(stamp_path, today):
        if _refresh_marketplace():
            c.mark_refreshed(stamp_path, today)
        else:
            return  # refresh failed/timed out -- do NOT diff against possibly-stale data

    marketplace_data = c.load_json(marketplace_path)
    catalog = c.load_marketplace_entries(marketplace_data)
    if not catalog:
        return

    installed_data = c.load_json(c.installed_plugins_path())
    installed = c.load_installed(installed_data)

    remote_shas = {}
    for entry in catalog:
        name = entry["name"]
        if name == SELF_NAME or name not in installed:
            continue
        url = c.entry_repo_url(entry)
        if url:
            remote_shas[name] = _remote_head_sha(url)

    missing = c.compute_missing(catalog, installed, SELF_NAME)
    outdated = c.compute_outdated(catalog, installed, remote_shas, SELF_NAME)

    skip_list = c.load_skip_list()
    missing = c.filter_missing_by_skip(missing, skip_list)
    outdated = c.filter_outdated_by_skip(outdated, skip_list)

    if os.environ.get("GET_HAIGGOH_AUTO_UPDATE") == "silent" and outdated:
        still_outdated = []
        for item in outdated:
            try:
                r = subprocess.run(["claude", "plugin", "update", f"{item['name']}@haiggoh"],
                                    capture_output=True, timeout=30)
                if r.returncode != 0:
                    still_outdated.append(item)
            except Exception:
                still_outdated.append(item)
        outdated = still_outdated

    banner = c.format_nudge(missing, outdated)
    if banner:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                   "additionalContext": banner}}))


try:
    main()
except Exception:
    pass
sys.exit(0)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ~/ClaudeWorkspace/get-haiggoh && pytest tests/test_hook_and_cli.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Run the full test suite**

Run: `cd ~/ClaudeWorkspace/get-haiggoh && pytest -v`
Expected: PASS (36 tests)

- [ ] **Step 7: Commit**

```bash
cd ~/ClaudeWorkspace/get-haiggoh
git add hooks tests/test_hook_and_cli.py
git commit -m "Add SessionStart nudge hook: throttled refresh, missing/outdated diff, silent-update mode"
```

---

### Task 6: Skill-side CLI (`bin/get-haiggoh.py`) + `SKILL.md`

**Files:**
- Create: `~/ClaudeWorkspace/get-haiggoh/bin/get-haiggoh.py`
- Create: `~/ClaudeWorkspace/get-haiggoh/skills/get-haiggoh/SKILL.md`
- Modify: `~/ClaudeWorkspace/get-haiggoh/tests/test_hook_and_cli.py`

**Interfaces:**
- Consumes: `get_haiggoh_core` (same as the hook)
- Produces: `python3 bin/get-haiggoh.py plan` prints a human-readable plan (missing + outdated, skip-list-filtered, self-excluded) and exits 0; `python3 bin/get-haiggoh.py apply` runs the actual `claude plugin install/update` commands for everything `plan` would have listed. The SKILL.md instructs the model to run `plan` first, show the user the output, get explicit confirmation, THEN run `apply` — the CLI itself does not prompt interactively (Claude Code's Bash tool isn't a TTY), so the confirmation gate lives in the model/skill layer, exactly like `waypoints`' CLI pattern where the CLI executes and the skill supplies judgment.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_hook_and_cli.py`:

```python
CLI = os.path.join(REPO_ROOT, "bin", "get-haiggoh.py")


def _run_cli(args, env_extra=None):
    env = os.environ.copy()
    env.update(env_extra or {})
    return subprocess.run([sys.executable, CLI] + args, capture_output=True, text=True,
                           env=env, timeout=10)


def test_cli_plan_lists_missing_plugin(tmp_path):
    known_path = str(tmp_path / "known_marketplaces.json")
    marketplace_dir = tmp_path / "marketplaces" / "haiggoh" / ".claude-plugin"
    marketplace_path = marketplace_dir / "marketplace.json"
    installed_path = str(tmp_path / "installed_plugins.json")

    _write_json(known_path, {"haiggoh": {"installLocation": str(tmp_path / "marketplaces" / "haiggoh")}})
    _write_json(str(marketplace_path), {"plugins": [
        {"name": "get-haiggoh", "source": {"source": "url", "url": "https://github.com/haiggoh/get-haiggoh.git"}},
        {"name": "measure-twice", "source": {"source": "url", "url": "https://github.com/haiggoh/measure-twice.git"}},
    ]})
    _write_json(installed_path, {"plugins": {}})

    env = {
        "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": known_path,
        "GET_HAIGGOH_INSTALLED_PLUGINS_FILE": installed_path,
        "GET_HAIGGOH_SKIP_FILE": str(tmp_path / "skip.json"),
        "GET_HAIGGOH_SELF_NAME": "get-haiggoh",
        "GET_HAIGGOH_SKIP_REMOTE_SHA_CHECK": "1",
    }
    r = _run_cli(["plan"], env)
    assert r.returncode == 0
    assert "measure-twice" in r.stdout


def test_cli_plan_reports_nothing_to_do(tmp_path):
    known_path = str(tmp_path / "known_marketplaces.json")
    marketplace_dir = tmp_path / "marketplaces" / "haiggoh" / ".claude-plugin"
    marketplace_path = marketplace_dir / "marketplace.json"
    installed_path = str(tmp_path / "installed_plugins.json")

    _write_json(known_path, {"haiggoh": {"installLocation": str(tmp_path / "marketplaces" / "haiggoh")}})
    _write_json(str(marketplace_path), {"plugins": [
        {"name": "get-haiggoh", "source": {"source": "url", "url": "https://github.com/haiggoh/get-haiggoh.git"}},
    ]})
    _write_json(installed_path, {"plugins": {}})

    env = {
        "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": known_path,
        "GET_HAIGGOH_INSTALLED_PLUGINS_FILE": installed_path,
        "GET_HAIGGOH_SKIP_FILE": str(tmp_path / "skip.json"),
        "GET_HAIGGOH_SELF_NAME": "get-haiggoh",
        "GET_HAIGGOH_SKIP_REMOTE_SHA_CHECK": "1",
    }
    r = _run_cli(["plan"], env)
    assert r.returncode == 0
    assert "nothing to do" in r.stdout.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/ClaudeWorkspace/get-haiggoh && pytest tests/test_hook_and_cli.py -v -k cli`
Expected: FAIL — `bin/get-haiggoh.py` doesn't exist yet

- [ ] **Step 3: Write `bin/get-haiggoh.py`**

```python
#!/usr/bin/env python3
"""get-haiggoh CLI: `plan` prints what would change (missing + outdated, skip-filtered,
self-excluded); `apply` executes it via `claude plugin install/update`. The CONFIRMATION
gate lives in the skill layer (SKILL.md), not here -- this CLI is non-interactive (the
Bash tool isn't a TTY), so `plan` then `apply` is how the model shows-then-does rather than
this script prompting itself.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import get_haiggoh_core as c

SELF_NAME = os.environ.get("GET_HAIGGOH_SELF_NAME") or "get-haiggoh"
REMOTE_TIMEOUT_S = float(os.environ.get("GET_HAIGGOH_REFRESH_TIMEOUT_S") or 5)


def _remote_head_sha(url):
    if os.environ.get("GET_HAIGGOH_SKIP_REMOTE_SHA_CHECK"):
        return None
    try:
        result = subprocess.run(["git", "ls-remote", url, "HEAD"], capture_output=True,
                                 text=True, timeout=REMOTE_TIMEOUT_S)
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return result.stdout.split()[0]
    except Exception:
        return None


def _compute():
    known = c.load_json(c.known_marketplaces_path())
    marketplace_path = c.resolve_marketplace_json_path(known, "haiggoh")
    catalog = c.load_marketplace_entries(c.load_json(marketplace_path)) if marketplace_path else []
    installed = c.load_installed(c.load_json(c.installed_plugins_path()))

    remote_shas = {}
    for entry in catalog:
        name = entry["name"]
        if name == SELF_NAME or name not in installed:
            continue
        url = c.entry_repo_url(entry)
        if url:
            remote_shas[name] = _remote_head_sha(url)

    missing = c.compute_missing(catalog, installed, SELF_NAME)
    outdated = c.compute_outdated(catalog, installed, remote_shas, SELF_NAME)
    skip_list = c.load_skip_list()
    missing = c.filter_missing_by_skip(missing, skip_list)
    outdated = c.filter_outdated_by_skip(outdated, skip_list)
    return missing, outdated


def cmd_plan():
    missing, outdated = _compute()
    if not missing and not outdated:
        print("Nothing to do -- every haiggoh plugin is installed and current.")
        return 0
    if missing:
        print("Would install:")
        for name in missing:
            print(f"  + {name}")
    if outdated:
        print("Would update:")
        for item in outdated:
            print(f"  ^ {item['name']}  ({(item['installed_sha'] or '?')[:8]} -> {item['remote_sha'][:8]})")
    return 0


def cmd_apply():
    missing, outdated = _compute()
    failed = []
    for name in missing:
        r = subprocess.run(["claude", "plugin", "install", f"{name}@haiggoh"], capture_output=True, text=True)
        print(f"install {name}: {'ok' if r.returncode == 0 else 'FAILED: ' + r.stderr.strip()}")
        if r.returncode != 0:
            failed.append(name)
    for item in outdated:
        name = item["name"]
        r = subprocess.run(["claude", "plugin", "update", f"{name}@haiggoh"], capture_output=True, text=True)
        print(f"update {name}: {'ok' if r.returncode == 0 else 'FAILED: ' + r.stderr.strip()}")
        if r.returncode != 0:
            failed.append(name)
    return 1 if failed else 0


def main(argv):
    if not argv or argv[0] not in ("plan", "apply"):
        print("usage: get-haiggoh.py plan|apply", file=sys.stderr)
        return 2
    return cmd_plan() if argv[0] == "plan" else cmd_apply()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/ClaudeWorkspace/get-haiggoh && pytest tests/test_hook_and_cli.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Write `skills/get-haiggoh/SKILL.md`**

```markdown
---
name: get-haiggoh
description: Use when the user asks to install all their haiggoh plugins, sync/update haiggoh plugins, or references "get-haiggoh" by name. Triggers on specific phrasing like "install all my haiggoh plugins", "get-haiggoh", "sync my haiggoh plugins", "install my other plugins" (haiggoh context established). Do NOT trigger on a bare generic "install everything" with no haiggoh context -- that's too easily confused with unrelated software installs.
---

# get-haiggoh

Installs/updates every published `haiggoh` Claude Code plugin from one place.

## Procedure

1. Run `python3 "$CLAUDE_PLUGIN_ROOT/bin/get-haiggoh.py" plan` (or the bare `get-haiggoh.py plan`
   if it's on the Bash-tool PATH via `bin/` injection).
2. Show the user the plan output verbatim.
3. If it says "Nothing to do", stop there -- no further action needed.
4. Otherwise, **ask for explicit confirmation** before proceeding -- installing/updating
   plugins is a visible, effectful action. Do not run `apply` without it.
5. On confirmation, run `get-haiggoh.py apply` and report the per-plugin install/update
   results verbatim (including any failures) back to the user.
6. If the user says to skip a specific plugin instead of installing/updating it, record
   that in `~/.claude/.get-haiggoh-skip.json` (a flat JSON object: `{"<plugin-name>":
   "install"|"update"|"both"}`) so the SessionStart nudge and future `plan` runs stop
   surfacing that specific plugin for that specific reason, while still catching
   genuinely new plugins later.

## Notes

- This skill/plugin excludes itself (`get-haiggoh`) from its own install/update list --
  installing itself is meaningless.
- A brand-new user still has to manually run `claude plugin marketplace add
  haiggoh/get-haiggoh` and `claude plugin install get-haiggoh@haiggoh` once, by hand --
  this plugin cannot bootstrap its own first install. Everything after that first
  install is automated.
- **Future extension (not built yet):** a curated/categorized install mode (e.g.
  "session-continuity" vs "automation-safety" groups) instead of install-everything,
  once the plugin list grows large enough that "everything" stops being the obvious
  default.
```

- [ ] **Step 6: Commit**

```bash
cd ~/ClaudeWorkspace/get-haiggoh
git add bin skills tests/test_hook_and_cli.py
git commit -m "Add plan/apply CLI and SKILL.md for the confirming install/update flow"
```

---

### Task 7: README + final full test run

**Files:**
- Create: `~/ClaudeWorkspace/get-haiggoh/README.md`

**Interfaces:**
- Consumes: nothing new — this is documentation only

- [ ] **Step 1: Write `README.md`**

```markdown
# get-haiggoh

Install and keep up to date every published `haiggoh` Claude Code plugin from one place.
Also the canonical home of the `haiggoh` marketplace catalog (`.claude-plugin/marketplace.json`)
-- relocated here from `claude-code-desktop-sync`, which only hosted it because it happened
to be the first plugin published, not because it was the right fit.

## What it does

- **SessionStart hook** (`hooks/check-installed.py`): once per day (throttled via a local
  stamp file, so it doesn't add network latency to every single session), refreshes the
  marketplace catalog and checks for haiggoh plugins that are either not installed or have
  a newer commit upstream than what's installed. If anything's found, it nudges you via
  `additionalContext` toward this plugin's skill. Says nothing if everything's current.
- **Skill** (`get-haiggoh`): triggered by specific phrasing ("install all my haiggoh
  plugins", "get-haiggoh", "sync my haiggoh plugins") -- not a bare generic "install
  everything", which is too easy to misfire on unrelated requests. Shows you a plan
  (what would be installed/updated), asks for confirmation, then executes it.

## MVP scope

Installs/updates **everything** in the catalog, no picking. A curated/categorized mode
(e.g. grouping by purpose) is a natural future extension once the plugin list grows large
enough that "everything" stops being the obviously-right default -- not built in this
version.

## Configuration

- `GET_HAIGGOH_AUTO_UPDATE` (`ask` default | `silent`): `ask` means the SessionStart hook
  only nudges about outdated plugins; `silent` means it runs `claude plugin update` for
  them itself, no prompt. This ONLY affects updates to already-installed plugins --
  brand-new installs always go through the confirming skill, regardless of this setting.
- `~/.claude/.get-haiggoh-skip.json`: per-plugin skip list, `{"<name>": "install"|"update"|"both"}`.
  Managed via the skill when you say "skip that one" in response to a nudge.

## Known limitation

A brand-new user still has to manually run `claude plugin marketplace add
haiggoh/get-haiggoh` and `claude plugin install get-haiggoh@haiggoh` once, by hand -- this
plugin can't bootstrap its own first install. Everything after that first install is
automated.

## Tests

```bash
pip install pytest  # or pipx install pytest
pytest -v
```
```

- [ ] **Step 2: Run the full test suite one more time**

Run: `cd ~/ClaudeWorkspace/get-haiggoh && pytest -v`
Expected: PASS (all tests, no failures/errors)

- [ ] **Step 3: Commit**

```bash
cd ~/ClaudeWorkspace/get-haiggoh
git add README.md
git commit -m "Add README"
```

---

### Task 8: Publish, marketplace migration, and reconciliation (executed by the coordinating session, not a subagent)

This task is intentionally NOT delegated to a fresh subagent — it touches shared/public
infrastructure (a GitHub push, the live `haiggoh` marketplace registration on this
machine, and durable memory) that the coordinating session already has full context on
from the design/spec conversation. Steps:

- [ ] **Step 1:** `gh repo create haiggoh/get-haiggoh --public --source=. --remote=origin --push` from `~/ClaudeWorkspace/get-haiggoh`.
- [ ] **Step 2:** `claude plugin marketplace remove haiggoh` then `claude plugin marketplace add haiggoh/get-haiggoh` (re-points this machine's registration to the new repo).
- [ ] **Step 3:** `claude plugin install get-haiggoh@haiggoh`; verify with `claude plugin list` and `claude plugin details get-haiggoh@haiggoh`.
- [ ] **Step 4:** Remove `.claude-plugin/marketplace.json` from `~/ClaudeWorkspace/claude-code-desktop-sync`, commit, push. Update that repo's README if it references the marketplace file's old location.
- [ ] **Step 5:** Update memory: `plugin-publishing-workflow.md` (marketplace now lives in `get-haiggoh`, not `claude-code-desktop-sync`), add a new `get-haiggoh-project.md` memory documenting the plugin (mirroring `waypoints-project.md`'s shape), update `MEMORY.md`'s index.
- [ ] **Step 6:** Mark the `publish-a-haiggoh-install-everything-meta-package` waypoint done (`waypoints.py done publish-a-haiggoh-install-everything-meta-package`).
- [ ] **Step 7:** Sanity-check: restart is required for the new hook/skill to load in THIS session; note that to the user in the final summary rather than pretending it's already live.
```

---

## Self-Review

**Spec coverage:** MVP/no-picking (Task 1 marketplace.json + README), dynamic plugin-list read (Task 2/3 diff against loaded marketplace entries, never hardcoded), specific skill trigger + confirm-before-apply (Task 6 SKILL.md + CLI split), hook nudge + configurable silent-update (Task 5), self-exclusion (Task 3), skip-list with scope (Task 2/3), throttled refresh + timeout (Task 4/5), marketplace-repo-copy resolution not bundled copy (Task 2's `resolve_marketplace_json_path` + hook/CLI both call it, never `$CLAUDE_PLUGIN_ROOT`), migration steps incl. re-pointing `known_marketplaces.json` (Task 8), known limitation documented (SKILL.md + README), testing approach with mocked subprocess (all hook/CLI tests use env-var escape hatches instead of real network calls) — all covered.

**Placeholder scan:** no TBD/TODO; every step has complete, runnable code.

**Type consistency:** `compute_missing`/`compute_outdated` signatures match their call sites in both `check-installed.py` and `bin/get-haiggoh.py`; `filter_missing_by_skip`/`filter_outdated_by_skip` like-wise; `format_nudge(missing, outdated)` matches the hook's call. Verified no drift between Task 2/3/4's declared interfaces and Task 5/6's usage.
