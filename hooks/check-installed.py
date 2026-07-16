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
