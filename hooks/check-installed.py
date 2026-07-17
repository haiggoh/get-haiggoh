#!/usr/bin/env python3
"""get-haiggoh -- SessionStart hook: throttled marketplace refresh + missing-plugin nudge.

Reads the MARKETPLACE-REPO copy of marketplace.json (resolved via known_marketplaces.json's
installLocation), diffs it against installed_plugins.json for MISSING plugins only, filters
through the skip-list, and emits a nudge via additionalContext. Nothing is printed if there's
nothing to report. Fail-safe throughout: any error -> exit 0, no output, never blocks a
session. This hook NEVER installs anything itself -- a brand-new install always routes
through the confirming skill.

Outdated (version-drift) detection intentionally lives ONLY in `bin/get-haiggoh.py plan`, not
here: it requires a `git ls-remote` per installed catalog entry, which is cheap to pay once
when the user explicitly asks but too expensive to pay unconditionally on every session start
(this hook already runs alongside 7+ other haiggoh SessionStart hooks).
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

    missing = c.compute_missing(catalog, installed, SELF_NAME)

    skip_list = c.load_skip_list()
    missing = c.filter_missing_by_skip(missing, skip_list)

    banner = c.format_nudge(missing, [])
    if banner:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                   "additionalContext": banner}}))


try:
    main()
except Exception:
    pass
sys.exit(0)
