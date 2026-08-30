"""Pure, unit-testable core for get-haiggoh.

No subprocess/network calls live here — hooks/check-installed.py and bin/get-haiggoh.py
are the only places that shell out to `claude`/`git`, so this module stays trivially
mockable in tests. Every loader is fail-safe (returns an empty structure on error) —
a corrupt/missing file must never crash a SessionStart hook.
"""
import json
import os
import re
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
    """Return {plugin_name: {"version": str|None, "installPath": str|None}} for every
    installed_plugins.json key ending in marketplace_suffix. Takes the FIRST scope entry
    per plugin (mirrors how these plugins are installed today: one scope each).

    `gitCommitSha` is deliberately NOT read. The harness writes it once at first install and
    never rewrites it, so it is stale for every plugin that has been updated even once --
    reading it at all invites a caller to compare against it again. `version` and
    `installPath` are the two fields measured accurate in 11/11 plugins on 2026-08-30."""
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
            "installPath": first.get("installPath"),
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


def plugin_manifest_url(git_url):
    """Turn a GitHub repo URL into the raw URL of that repo's .claude-plugin/plugin.json at
    HEAD -- the REMOTE side of the version comparison. Returns None for anything that isn't a
    recognizable GitHub owner/repo URL, and callers must treat None as "unknown" rather than
    as outdated. Accepts the https, ssh and scp-style forms, with or without a `.git` suffix."""
    if not isinstance(git_url, str):
        return None
    match = re.fullmatch(
        r"(?:https?://(?:www\.)?github\.com/|ssh://git@github\.com/|git@github\.com:)"
        r"([^/]+)/([^/]+?)(?:\.git)?/?",
        git_url.strip())
    if not match:
        return None
    owner, repo = match.groups()
    return (f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD"
            "/.claude-plugin/plugin.json")


def parse_version(text):
    """A dotted-numeric version as a comparable tuple, or None if it isn't one. A leading
    `v` is tolerated and a `-rc1`/`+build` suffix is IGNORED for ordering, so 0.4.0-rc1 and
    0.4.0 compare EQUAL -- deliberate: this tool only ever needs "is the published version
    ahead of mine", and pre-release ordering is not worth a false nag either way."""
    if not isinstance(text, str):
        return None
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)(?:[-+].*)?", text.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def remote_is_newer(installed_version, remote_version):
    """True only when the remote version is demonstrably AHEAD of the installed one.

    Falls silent (False) whenever either side is unknown -- a failed fetch or a manifest
    with no version must never manufacture an "update available". Unequal-length versions
    are zero-padded, so 0.4 and 0.4.0 are the same version. If either string is not
    dotted-numeric at all, this degrades to plain inequality, which is the old
    strict-difference behaviour for the one case where ordering is undefined."""
    if not installed_version or not remote_version:
        return False
    left, right = parse_version(installed_version), parse_version(remote_version)
    if left is None or right is None:
        return installed_version.strip() != remote_version.strip()
    width = max(len(left), len(right))
    left += (0,) * (width - len(left))
    right += (0,) * (width - len(right))
    return right > left


def compute_outdated(catalog_entries, installed, remote_versions, self_name):
    """Installed entries whose PUBLISHED version is ahead of the installed version,
    excluding self_name.

    Compares versions, NOT commit shas. Measured 2026-08-30 on harness 2.1.246 across all 11
    haiggoh plugins: installed_plugins.json keeps `version` and `installPath` accurate in
    11/11 cases, while `gitCommitSha` has never been rewritten since first install (one plugin
    still recorded its initial commit across three version bumps). Comparing that field
    against remote HEAD therefore reported a phantom update for almost every plugin, every
    session, which made a REAL pending update indistinguishable from the noise. Both sides of
    the version comparison are accurate and cost the same one network call per plugin.

    A same-version push is deliberately NOT reported: the install path is keyed on the
    version (~/.claude/plugins/cache/<owner>/<name>/<version>/), so an update that doesn't
    bump plugin.json has nowhere new to land and is a silent no-op -- nagging about it could
    never be satisfied."""
    out = []
    for e in catalog_entries:
        name = e["name"]
        if name == self_name or name not in installed:
            continue
        remote_version = remote_versions.get(name)
        installed_version = installed[name].get("version")
        if remote_is_newer(installed_version, remote_version):
            out.append({"name": name, "installed_version": installed_version,
                        "remote_version": remote_version})
    return out


def filter_missing_by_skip(missing, skip_list):
    return [name for name in missing if skip_list.get(name) not in ("install", "both")]


def filter_outdated_by_skip(outdated, skip_list):
    return [item for item in outdated if skip_list.get(item["name"]) not in ("update", "both")]


def filter_catalog_by_selection(catalog_entries, names=None, category=None):
    """Narrow catalog entries to an explicit name list and/or a category, for selective
    install/update (--only, --category). Both filters are AND'd when both are given.
    None/empty means "no filter on that axis" -- so calling with neither returns the
    catalog unchanged. `names` is matched case-sensitively against entry["name"]; unknown
    names are silently dropped (not an error) so a typo just yields an empty selection
    rather than crashing a SessionStart-adjacent call."""
    out = catalog_entries
    if names:
        wanted = set(names)
        out = [e for e in out if e["name"] in wanted]
    if category:
        out = [e for e in out if e.get("category") == category]
    return out


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


def save_refresh_state(stamp_path, today_str, remote_versions):
    """Like mark_refreshed, but also caches the day's remote plugin VERSIONS alongside the
    date (Option B): the once-per-day network fetch is paid on the refresh, and every later
    same-day boot reads this cache to still surface outdated nudges WITHOUT a network hit.
    Atomic write. should_refresh() only reads `.date`, so it is unaffected by the extra key.
    `remote_versions` is {plugin_name: version_str|None}.

    The cache key is `remote_versions`; a stamp written by an older release carries
    `remote_shas` instead, which load_cached_versions ignores -- so the day it upgrades, the
    nudge simply stays silent until the next daily refresh rather than comparing a version
    against a sha."""
    os.makedirs(os.path.dirname(stamp_path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(stamp_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump({"date": today_str, "remote_versions": remote_versions or {}}, f)
        os.replace(tmp, stamp_path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def load_cached_versions(stamp_path):
    """Remote versions cached by the last save_refresh_state, or {} if absent/malformed (which
    includes a legacy stamp holding `remote_shas`). Used on same-day boots to compute outdated
    without re-fetching. compute_outdated treats a missing or None version as 'unknown' and
    never manufactures a false positive from it."""
    cached = load_json(stamp_path).get("remote_versions")
    return cached if isinstance(cached, dict) else {}


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
        lines.append(f"  ^ {item['name']} {item['installed_version']} -> "
                     f"{item['remote_version']} (update available)")
    return "\n".join(lines)
