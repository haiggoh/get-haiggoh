#!/usr/bin/env python3
"""get-haiggoh -- SessionStart hook: throttled marketplace refresh + missing-plugin nudge.

Reads the MARKETPLACE-REPO copy of marketplace.json (resolved via known_marketplaces.json's
installLocation), diffs it against installed_plugins.json for MISSING plugins only, filters
through the skip-list, and emits a nudge via additionalContext. Nothing is printed if there's
nothing to report. Fail-safe throughout: any error -> exit 0, no output, never blocks a
session. This hook NEVER installs anything itself -- a brand-new install always routes
through the confirming skill.

Outdated (version-drift) detection compares the installed plugin VERSION against the version
published in the repo's own .claude-plugin/plugin.json at HEAD. It does NOT compare commit
shas: the harness writes installed_plugins.json's `gitCommitSha` once at first install and
never rewrites it, so sha-comparison reported a phantom update for nearly every plugin on
every boot, which is exactly what made a real pending update invisible in the noise.

It uses the "Option B" cache strategy: the remote sweep is expensive to pay on every session
start (this hook runs alongside 7+ other haiggoh SessionStart hooks), so it is gated behind
the same once-per-day `should_refresh()` stamp as the marketplace refresh AND the fetched
versions are cached alongside the stamp. Same-day boots read the cache and still surface
outdated nudges with NO network hit; the sweep is paid at most once per day (in parallel,
bounded). A failed/partial sweep falls silent — never a false "update available".
"""
import json
import os
import subprocess
import sys
import urllib.request

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


def _remote_plugin_version(url):
    """The `version` published in the repo's .claude-plugin/plugin.json at HEAD, or None on
    any failure/timeout (which compute_outdated treats as 'unknown', never a false positive)."""
    if os.environ.get("GET_HAIGGOH_SKIP_REMOTE_VERSION_CHECK") \
            or os.environ.get("GET_HAIGGOH_SKIP_REMOTE_SHA_CHECK"):
        return None  # test-only escape hatch (both spellings honoured)
    manifest_url = c.plugin_manifest_url(url)
    if not manifest_url:
        return None
    try:
        with urllib.request.urlopen(manifest_url, timeout=REFRESH_TIMEOUT_S) as response:
            version = json.loads(response.read().decode("utf-8")).get("version")
        return version if isinstance(version, str) else None
    except Exception:
        return None


def _fetch_remote_versions(catalog, installed):
    """Parallel, bounded manifest sweep over installed catalog entries with a repo URL.
    Returns {plugin_name: version|None}. Paid at most once per day (gated by should_refresh in
    main). Fail-safe: any error -> whatever partial result we have."""
    targets = [(e["name"], c.entry_repo_url(e)) for e in catalog
               if e.get("name") and e["name"] != SELF_NAME and e["name"] in installed
               and c.entry_repo_url(e)]
    versions = {}
    if not targets:
        return versions
    try:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(8, len(targets))) as ex:
            for name, version in ex.map(lambda t: (t[0], _remote_plugin_version(t[1])), targets):
                versions[name] = version
    except Exception:
        pass
    return versions


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
    refreshing = c.should_refresh(stamp_path, today)
    if refreshing:
        if not _refresh_marketplace():
            return  # refresh failed/timed out -- do NOT diff against possibly-stale data

    marketplace_data = c.load_json(marketplace_path)
    catalog = c.load_marketplace_entries(marketplace_data)
    if not catalog:
        return

    installed_data = c.load_json(c.installed_plugins_path())
    installed = c.load_installed(installed_data)

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

    banner = c.format_nudge(missing, outdated)
    if banner:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                   "additionalContext": banner}}))


try:
    main()
except Exception:
    pass
sys.exit(0)
