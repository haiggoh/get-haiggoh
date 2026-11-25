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


def _fetch_remote_versions(catalog, installed):
    """Parallel, bounded manifest sweep over installed catalog entries with a repo URL, through
    the transport the CLI shares (core.fetch_url). Returns ({plugin_name: version|None},
    [names whose check RAN and failed]). Paid at most once per day (gated by should_refresh in
    main). A crash mid-sweep marks every target unverified rather than passing as complete."""
    targets = [(e["name"], c.entry_repo_url(e)) for e in catalog
               if e.get("name") and e["name"] != SELF_NAME and e["name"] in installed
               and c.entry_repo_url(e)]
    versions, unverified = {}, []
    if not targets:
        return versions, unverified
    try:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(8, len(targets))) as ex:
            for name, (version, diagnostic) in ex.map(
                    lambda t: (t[0], c.remote_plugin_version(t[1], REFRESH_TIMEOUT_S)), targets):
                versions[name] = version
                if diagnostic:
                    unverified.append(name)
    except Exception:
        return versions, [name for name, _ in targets]
    return versions, unverified


def _add_missing_shims(installed):
    """Create PATH shims that collide with nothing. Never overwrites or prefixes: that is an
    explicit `get-haiggoh shims apply --on-collision=...`. Returns a one-line note naming the
    shortcuts just CREATED ('' if none). Fail-safe: any error -> ''."""
    if os.environ.get("GET_HAIGGOH_NO_SHIMS"):
        return ""
    try:
        import get_haiggoh_shims as s
        created = []
        plan = s.plan_shims(installed, policy="skip")
        for act in plan:
            if act["action"] in ("create", "refresh"):
                s.apply_action(act)
                if act["action"] == "create":
                    created.append(act["name"])
        notes = [("👨🏻‍💻 get-haiggoh: added PATH shortcuts: " + ", ".join(created)) if created else ""]
        # a shortcut only helps once its directory is on the user's PATH (stock macOS: it is
        # not); ensure_on_path edits the login shell's startup file once and never raises
        if any(s.is_our_shim(act["path"]) for act in plan):
            import get_haiggoh_pathrc as pathrc
            notes.append(pathrc.ensure_on_path(s.shim_dir()))
        return "\n".join(n for n in notes if n)
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

    installed_data = c.load_json(c.installed_plugins_path())
    installed = c.load_installed(installed_data)

    # Option B: fetch remote versions at most once/day (on the refresh) and cache them
    # alongside the stamp; same-day boots reuse the cache so outdated nudges cost no network.
    unverified = []
    if refreshing:
        remote_versions, unverified = _fetch_remote_versions(catalog, installed)
        # date AND version cache -- but only for a complete sweep; a blind one retries next boot
        c.record_sweep(stamp_path, today, remote_versions, unverified)
    else:
        remote_versions = c.load_cached_versions(stamp_path)

    skip_list = c.load_skip_list()
    missing = c.filter_missing_by_skip(c.compute_missing(catalog, installed, SELF_NAME), skip_list)
    outdated = c.filter_outdated_by_skip(
        c.compute_outdated(catalog, installed, remote_versions, SELF_NAME), skip_list)

    return c.format_nudge(missing, outdated, unverified=unverified)


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return  # malformed stdin -- fail-safe, no output

    # Native Codex owns its registry. Never refresh Claude's marketplace or create
    # Claude shortcuts from a Codex session; recover only verified manual duplicates.
    import get_haiggoh_hook_health as health
    if health.is_codex_payload(payload):
        banner = health.codex_notice(payload)
        if banner:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                     "additionalContext": banner}}))
        return

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


if __name__ == "__main__":
    if sys.argv[1:]:
        if sys.argv[1:] in (["--help"], ["-h"]):
            print("check-installed.py — SessionStart: Claude plugin checks, or verified Codex manual-hook recovery. Usage: check-installed.py [--help]. Environment: CODEX_HOME selects Codex state; GET_HAIGGOH_* selects Claude check paths and refresh settings.")
            sys.exit(0)
        print("usage: check-installed.py [--help]", file=sys.stderr)
        sys.exit(2)
    try:
        main()
    except Exception as exc:
        print("get-haiggoh: startup check could not complete: " + type(exc).__name__, file=sys.stderr)
    sys.exit(0)
