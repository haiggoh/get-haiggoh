#!/usr/bin/env python3
"""get-haiggoh CLI: `plan` prints what would change (missing + outdated, skip-filtered,
self-excluded); `apply` executes it via `claude plugin install/update`. The CONFIRMATION
gate lives in the skill layer (SKILL.md), not here -- this CLI is non-interactive (the
Bash tool isn't a TTY), so `plan` then `apply` is how the model shows-then-does rather than
this script prompting itself.
"""
import json
import os
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import get_haiggoh_core as c

SELF_NAME = os.environ.get("GET_HAIGGOH_SELF_NAME") or "get-haiggoh"
REMOTE_TIMEOUT_S = float(os.environ.get("GET_HAIGGOH_REFRESH_TIMEOUT_S") or 5)


def _skip_remote_check():
    """Test-only escape hatch. `GET_HAIGGOH_SKIP_REMOTE_VERSION_CHECK` is the current name;
    the older `..._SHA_CHECK` spelling is still honoured so an existing test or wrapper that
    sets it keeps suppressing the network call instead of silently starting to make one."""
    return bool(os.environ.get("GET_HAIGGOH_SKIP_REMOTE_VERSION_CHECK")
                or os.environ.get("GET_HAIGGOH_SKIP_REMOTE_SHA_CHECK"))


def _remote_plugin_version(url):
    """The published `version` from the repo's .claude-plugin/plugin.json at HEAD, or None on
    any failure (which compute_outdated treats as 'unknown', never a false positive). One
    network call per plugin -- the same cost as the `git ls-remote` this replaced."""
    if _skip_remote_check():
        return None
    manifest_url = c.plugin_manifest_url(url)
    if not manifest_url:
        return None
    try:
        with urllib.request.urlopen(manifest_url, timeout=REMOTE_TIMEOUT_S) as response:
            version = json.loads(response.read().decode("utf-8")).get("version")
        return version if isinstance(version, str) else None
    except Exception:
        return None


def _compute(only=None, category=None):
    known = c.load_json(c.known_marketplaces_path())
    marketplace_path = c.resolve_marketplace_json_path(known, "haiggoh")
    catalog = c.load_marketplace_entries(c.load_json(marketplace_path)) if marketplace_path else []
    catalog = c.filter_catalog_by_selection(catalog, names=only, category=category)
    installed = c.load_installed(c.load_json(c.installed_plugins_path()))

    remote_versions = {}
    for entry in catalog:
        name = entry["name"]
        if name == SELF_NAME or name not in installed:
            continue
        url = c.entry_repo_url(entry)
        if url:
            remote_versions[name] = _remote_plugin_version(url)

    missing = c.compute_missing(catalog, installed, SELF_NAME)
    outdated = c.compute_outdated(catalog, installed, remote_versions, SELF_NAME)
    skip_list = c.load_skip_list()
    missing = c.filter_missing_by_skip(missing, skip_list)
    outdated = c.filter_outdated_by_skip(outdated, skip_list)
    return missing, outdated


def cmd_plan(only=None, category=None):
    missing, outdated = _compute(only=only, category=category)
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
            print(f"  ^ {item['name']}  ({item['installed_version'] or '?'} -> "
                  f"{item['remote_version']})")
    return 0


def _installed_now():
    """Re-read installed_plugins.json from disk, so a post-update check sees the harness's
    own record rather than the snapshot _compute took before anything ran."""
    return c.load_installed(c.load_json(c.installed_plugins_path()))


def cmd_apply(only=None, category=None):
    """Run the plan, then VERIFY each result by outcome instead of by exit status.

    `claude plugin update` exits 0 for "the clone succeeded", which is not the same as "this
    machine now runs that code": the install path is keyed on the version
    (~/.claude/plugins/cache/<owner>/<name>/<version>/), so an update with no version bump has
    nowhere new to land and leaves the existing directory untouched while still printing ok.
    Every line below therefore reports the version that is actually recorded afterwards, and a
    command that exited 0 without moving the version is reported NOT APPLIED and counted as a
    failure."""
    missing, outdated = _compute(only=only, category=category)
    failed = []
    for name in missing:
        r = subprocess.run(["claude", "plugin", "install", f"{name}@haiggoh"], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"install {name}: FAILED: {r.stderr.strip()}")
            failed.append(name)
            continue
        entry = _installed_now().get(name)
        if entry:
            print(f"install {name}: ok ({entry.get('version') or 'version unrecorded'})")
        else:
            print(f"install {name}: NOT APPLIED (exited 0 but it is still not installed)")
            failed.append(name)
    for item in outdated:
        name = item["name"]
        before = item["installed_version"]
        expected = item["remote_version"]
        r = subprocess.run(["claude", "plugin", "update", f"{name}@haiggoh"], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"update {name}: FAILED: {r.stderr.strip()}")
            failed.append(name)
            continue
        after = (_installed_now().get(name) or {}).get("version")
        if after == expected:
            print(f"update {name}: ok ({before or '?'} -> {after})")
        elif c.remote_is_newer(before, after):
            print(f"update {name}: ok ({before or '?'} -> {after}, expected {expected})")
        else:
            print(f"update {name}: NOT APPLIED (exited 0 but still {after or 'unrecorded'}, "
                  f"expected {expected})")
            failed.append(name)
    return 1 if failed else 0


def _parse_selection_args(argv):
    """Parse --only name1,name2 and --category NAME out of argv. Returns
    (only_names_or_None, category_or_None, leftover_unrecognized_args)."""
    only = None
    category = None
    leftover = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--only" and i + 1 < len(argv):
            only = [n.strip() for n in argv[i + 1].split(",") if n.strip()]
            i += 2
        elif arg.startswith("--only="):
            only = [n.strip() for n in arg[len("--only="):].split(",") if n.strip()]
            i += 1
        elif arg == "--category" and i + 1 < len(argv):
            category = argv[i + 1]
            i += 2
        elif arg.startswith("--category="):
            category = arg[len("--category="):]
            i += 1
        else:
            leftover.append(arg)
            i += 1
    return only, category, leftover


def print_help():
    """Print help message."""
    print("get-haiggoh CLI - Manage haiggoh plugins")
    print("")
    print("Usage:")
    print("  get-haiggoh.py plan [--only name1,name2] [--category NAME]")
    print("    Show what would be installed/updated (dry run)")
    print("")
    print("  get-haiggoh.py apply [--only name1,name2] [--category NAME]")
    print("    Actually install/update plugins")
    print("")
    print("Options:")
    print("  --only name1,name2  Limit operation to specific plugin names (comma-separated)")
    print("  --category NAME     Limit operation to plugins in specific category")
    print("  --help              Show this help message")
    print("")
    print("Examples:")
    print("  get-haiggoh.py plan")
    print("  get-haiggoh.py apply --only video-use,waypoints")
    print("  get-haiggoh.py plan --category utility")


def main(argv):
    # Handle --help flag
    if "--help" in argv:
        print_help()
        return 0

    if not argv or argv[0] not in ("plan", "apply"):
        print("usage: get-haiggoh.py plan|apply [--only name1,name2] [--category NAME]",
              file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    only, category, leftover = _parse_selection_args(rest)
    if leftover:
        print(f"usage: get-haiggoh.py {cmd} [--only name1,name2] [--category NAME]"
              f" (unrecognized: {' '.join(leftover)})", file=sys.stderr)
        return 2
    return cmd_plan(only=only, category=category) if cmd == "plan" \
        else cmd_apply(only=only, category=category)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
