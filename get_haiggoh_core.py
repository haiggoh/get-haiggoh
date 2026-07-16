"""Pure, unit-testable core for get-haiggoh.

No subprocess/network calls live here — hooks/check-installed.py and bin/get-haiggoh.py
are the only places that shell out to `claude`/`git`, so this module stays trivially
mockable in tests. Every loader is fail-safe (returns an empty structure on error) —
a corrupt/missing file must never crash a SessionStart hook.
"""
import json
import os
import tempfile
from datetime import date


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
