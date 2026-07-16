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
