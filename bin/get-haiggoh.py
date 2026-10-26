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

_skip_remote_check = c.skip_remote_check


def _remote_plugin_version(url):
    """(version, diagnostic) for the repo's HEAD manifest, via the transport the hook shares
    (core.fetch_url: urllib, then curl). A failure comes back as a diagnostic that plan and
    apply render LOUDLY -- never as a silent None that reads as 'current'."""
    return c.remote_plugin_version(url, REMOTE_TIMEOUT_S)


def _latest_tag(repo_url):
    """(tag, version_tuple) of the highest v-semver tag on the repo, or (None, None)."""
    if _skip_remote_check() or not repo_url:
        return None, None
    try:
        out = subprocess.run(["git", "ls-remote", "--tags", repo_url], capture_output=True,
                             text=True, timeout=REMOTE_TIMEOUT_S).stdout
    except Exception:
        return None, None
    tag = c.parse_latest_tag(out)
    return (tag, c.tag_version_tuple(tag)) if tag else (None, None)


SANDBOX_HINT = (
    "the sandbox denies writes under ~/.claude/plugins, so no in-session retry can succeed.\n"
    "    Run it OUTSIDE the sandbox — in Claude Code, prefix with `!` so it runs in your shell:\n"
    "      ! python {self} apply\n"
    "    This is a built-in Claude Code protection (write.denyWithinAllow), NOT a broken\n"
    "    filesystem: the directory is writable, and an explicit sandbox.write.allow for that\n"
    "    path does not override it. Do not chase ACLs, SIP, quotas or xattrs."
)


def _sandbox_denied(*outputs):
    """True if this failure looks like the sandbox refusing a plugin-cache write.

    Worth special-casing because the symptom lies: the denial surfaces as
    `Operation not permitted`, which is exactly what a real permission fault looks like.
    A remote session burned ~15 tool calls on read-only-filesystem, ACL, SIP, inode-quota
    and FinderInfo-xattr theories before the user supplied the one-line workaround. Naming
    the cause once is worth more than any number of retries.
    """
    blob = " ".join(o or "" for o in outputs).lower()
    denial = ("operation not permitted" in blob or "permission denied" in blob
              or "eperm" in blob or "read-only file system" in blob)
    if not denial:
        return False
    # Only claim the sandbox when we are plausibly inside one AND the cache is really writable
    # from an unsandboxed process — otherwise a genuine permission problem would be misreported.
    return _cache_is_writable_but_denied()


def _cache_is_writable_but_denied():
    """Distinguish 'the sandbox blocked us' from 'this path is genuinely unwritable'."""
    cache = os.path.expanduser("~/.claude/plugins/cache")
    if not os.path.isdir(cache):
        return False
    probe = os.path.join(cache, ".get-haiggoh-write-probe")
    try:
        os.mkdir(probe)
        os.rmdir(probe)
        return False          # we CAN write: the failure was something else entirely
    except OSError:
        return True           # we cannot — consistent with the sandbox deny list


def _explain_if_sandboxed(*outputs):
    """Print the actionable one-liner when the sandbox is the cause. Returns True if it was."""
    if not _sandbox_denied(*outputs):
        return False
    print("    " + SANDBOX_HINT.format(self=os.path.abspath(__file__)))
    return True


def _compute(only=None, category=None):
    known = c.load_json(c.known_marketplaces_path())
    marketplace_path = c.resolve_marketplace_json_path(known, "haiggoh")
    catalog = c.load_marketplace_entries(c.load_json(marketplace_path)) if marketplace_path else []
    catalog = c.filter_catalog_by_selection(catalog, names=only, category=category)
    installed = c.load_installed(c.load_json(c.installed_plugins_path()))

    # Parallel, bounded manifest sweep over installed catalog entries with a repo URL.
    # Same pattern as hooks/check-installed.py:_fetch_remote_versions
    # INCLUDE SELF_NAME (get-haiggoh) so it can update itself
    targets = [(e["name"], c.entry_repo_url(e)) for e in catalog
               if e.get("name") and e["name"] in installed
               and c.entry_repo_url(e)]
    remote_versions = {}
    diagnostics = {}
    repo_urls = dict(targets)
    if targets:
        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(8, len(targets))) as ex:
                for name, (version, diagnostic) in ex.map(
                        lambda t: (t[0], _remote_plugin_version(t[1])), targets):
                    remote_versions[name] = version
                    if diagnostic:
                        diagnostics[name] = diagnostic
        except Exception:
            pass

    missing = c.compute_missing(catalog, installed, SELF_NAME)
    outdated = c.compute_outdated(catalog, installed, remote_versions)
    skip_list = c.load_skip_list()
    missing = c.filter_missing_by_skip(missing, skip_list)
    outdated = c.filter_outdated_by_skip(outdated, skip_list)

    # Build full status for all catalog entries (including current ones)
    all_status = []
    for entry in catalog:
        name = entry["name"]
        # INCLUDE SELF_NAME (get-haiggoh) so it shows its own status
        inst = installed.get(name)
        remote_ver = remote_versions.get(name)
        installed_ver = inst.get("version") if inst else None

        if name in missing:
            all_status.append({"name": name, "status": "missing", "installed_version": None, "remote_version": None,
                               "diagnostic": diagnostics.get(name)})
        elif any(o["name"] == name for o in outdated):
            out = next(o for o in outdated if o["name"] == name)
            all_status.append({"name": name, "status": "outdated", "installed_version": out["installed_version"], "remote_version": out["remote_version"],
                               "diagnostic": diagnostics.get(name)})
        elif inst:
            diagnostic = diagnostics.get(name)
            # The deterministic tag check: when the HEAD manifest agrees with the installed
            # version but the repo's highest tag announces MORE, the tagged commit's manifest
            # was not bumped (or the tag points at the wrong commit) — exactly the shape that
            # hid free-agents 0.33.0. (0.9.0)
            if (remote_ver and installed_ver and remote_ver == installed_ver
                    and not _skip_remote_check()):
                tag, tag_tuple = _latest_tag(repo_urls.get(name))
                inst_tuple = c.tag_version_tuple(installed_ver)
                if tag and tag_tuple and inst_tuple and tag_tuple > inst_tuple:
                    diagnostic = {"url": repo_urls.get(name),
                                  "problem": (f"the latest tag {tag} announces a NEWER version than "
                                              f"the HEAD manifest publishes ({installed_ver})"),
                                  "meaning": ("the tagged commit's manifest was not bumped, or the "
                                              "tag points at the wrong commit — version-keyed "
                                              "installers compare the HEAD manifest and will never "
                                              "see the tagged version"),
                                  "fix": (f"align the version surfaces on the default branch "
                                          f"(plugin.json must say {tag[1:]}) and move the tag onto "
                                          "the corrected commit, saying plainly that it moved")}
            # A plugin whose published version could not be checked is UNVERIFIED, never
            # "current": rendering it as current is the silent-miss shape (0.9.1).
            all_status.append({"name": name, "status": "unverified" if diagnostic else "current",
                               "installed_version": installed_ver, "remote_version": remote_ver,
                               "diagnostic": diagnostic})
        elif name == SELF_NAME:
            # Self plugin (get-haiggoh) is not installed but not "missing" — treat as current
            # since it's the tool itself managing the marketplace
            diagnostic = diagnostics.get(name)
            all_status.append({"name": name, "status": "unverified" if diagnostic else "current",
                               "installed_version": "self", "remote_version": remote_ver,
                               "diagnostic": diagnostic})
        else:
            all_status.append({"name": name, "status": "unknown", "installed_version": None, "remote_version": None,
                               "diagnostic": None})
    return missing, outdated, all_status


def _render_status(missing, outdated, all_status):
    """Print the full status, shared by plan and apply so neither can drift back to silence.
    Returns the list of flagged (unverifiable) entries; callers exit non-zero on any."""
    # DIAGNOSE LOUDLY (0.9.0): a plugin whose published manifest cannot be verified is the
    # silent-miss shape that hid free-agents 0.33.0 for hours — render the diagnosis before
    # anything that could read as "all fine".
    flagged = [s for s in all_status if s.get("diagnostic")]
    for item in flagged:
        d = item["diagnostic"]
        print(f"⚠ {item['name']}: CANNOT VERIFY THE PUBLISHED VERSION")
        print(f"    fetched: {d['url']}")
        print(f"    problem: {d['problem']}")
        print(f"    meaning: {d['meaning']}")
        print(f"    fix:     {d['fix']}")

    # Always show full status - never silently return
    if missing:
        print("Would install:")
        for name in missing:
            print(f"  + {name}")
    if outdated:
        print("Would update:")
        for item in outdated:
            print(f"  ^ {item['name']}  ({item['installed_version'] or '?'} -> "
                  f"{item['remote_version']})")

    # List current plugins with version
    current_plugins = [s for s in all_status if s["status"] == "current"]
    if current_plugins:
        print("Current:")
        for item in current_plugins:
            ver = item['installed_version'] or '?'
            print(f"  = {item['name']}  {ver} (current)")

    unverified = [s for s in all_status if s["status"] == "unverified"]
    if unverified:
        print("Unverified (published version could not be checked — see ⚠ above):")
        for item in unverified:
            print(f"  ? {item['name']}  {item['installed_version'] or '?'} (unverified)")

    # Show other statuses
    missing_status = [s for s in all_status if s["status"] == "missing"]
    if missing_status:
        print("Missing (not installed):")
        for item in missing_status:
            print(f"  - {item['name']} (not installed)")

    unknown_plugins = [s for s in all_status if s["status"] == "unknown"]
    if unknown_plugins:
        print("Unknown status:")
        for item in unknown_plugins:
            print(f"  ? {item['name']}")

    if not missing and not outdated and not missing_status and not unknown_plugins and not flagged:
        print("All haiggoh plugins are current.")

    return flagged


def cmd_plan(only=None, category=None):
    """Exit 0 only when every plugin's state is known; 1 when any published version could not
    be verified, so a script (rtc-ship's refresh, a CI check) cannot read blindness as success."""
    missing, outdated, all_status = _compute(only=only, category=category)
    return 1 if _render_status(missing, outdated, all_status) else 0


def _installed_now():
    """Re-read installed_plugins.json from disk, so a post-update check sees the harness's
    own record rather than the snapshot _compute took before anything ran."""
    return c.load_installed(c.load_json(c.installed_plugins_path()))


def cmd_apply(only=None, category=None, policy="skip"):
    """Run the plan, then VERIFY each result by outcome instead of by exit status.

    `claude plugin update` exits 0 for "the clone succeeded", which is not the same as "this
    machine now runs that code": the install path is keyed on the version
    (~/.claude/plugins/cache/<owner>/<name>/<version>/), so an update with no version bump has
    nowhere new to land and leaves the existing directory untouched while still printing ok.
    Every line below therefore reports the version that is actually recorded afterwards, and a
    command that exited 0 without moving the version is reported NOT APPLIED and counted as a
    failure."""
    missing, outdated, all_status = _compute(only=only, category=category)

    # Same renderer as plan: before 0.9.1 apply had its own copy that never printed the
    # diagnostics, so an unverifiable plugin showed only as '(current)'.
    flagged = _render_status(missing, outdated, all_status)

    print()  # blank line before apply actions

    failed = [item["name"] for item in flagged]
    for name in missing:
        r = subprocess.run(["claude", "plugin", "install", f"{name}@haiggoh"], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"install {name}: FAILED: {r.stderr.strip()}")
            _explain_if_sandboxed(r.stderr, r.stdout)
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
            _explain_if_sandboxed(r.stderr, r.stdout)
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
    if not os.environ.get("GET_HAIGGOH_NO_SHIMS"):
        if cmd_shims("apply", only=only, policy=policy):
            failed.append("shims")
    return 1 if failed else 0


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
        return "skip", leftover, (
            f"--on-collision must be one of {', '.join(s.POLICIES)} (got {policy!r})")
    return policy, leftover, None


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
    print("get-haiggoh CLI - install, update and put on PATH every published haiggoh plugin")
    print()
    print("Usage:")
    print("  get-haiggoh                        (no arguments) open the interactive menu")
    print("  get-haiggoh plan    [--only n1,n2] [--category NAME]")
    print("      Show what would be installed/updated (dry run)")
    print("  get-haiggoh apply   [--only n1,n2] [--category NAME] [--on-collision POLICY]")
    print("  get-haiggoh upgrade [...same...]    alias of apply")
    print("      Install/update plugins, then create their PATH shortcuts")
    print("  get-haiggoh shims [plan|apply] [--only n1,n2] [--on-collision POLICY]")
    print("      Only the PATH shortcuts. Bare `shims` is a dry run (same as `shims plan`)")
    print()
    print("Options:")
    print("  --only name1,name2     Limit to specific plugin names (comma-separated)")
    print("  --category NAME        Limit to plugins in a specific category")
    print("  --on-collision POLICY  What to do when a command name is already taken by something")
    print("                         that is not a haiggoh shim: skip (default, reported),")
    print("                         overwrite (old link/file is backed up first), or")
    print("                         prefix (install it as haiggoh-<name>)")
    print("  --help                 Show this help message")
    print()
    print("Environment:")
    print("  GET_HAIGGOH_NO_SHIMS=1         never create shortcuts (apply and the SessionStart hook)")
    print("  GET_HAIGGOH_SHIM_DIR           where shortcuts go (default ~/.local/bin)")
    print("  GET_HAIGGOH_SHIM_BACKUP_DIR    where overwritten links/files are recorded")
    print("                                 (default ~/.local/state/get-haiggoh/shim-backups)")
    print("  GET_HAIGGOH_INSTALLED_PLUGINS_FILE, GET_HAIGGOH_CACHE_DIR")
    print("                                 override what the shortcuts resolve against")
    print("  GET_HAIGGOH_CURL               curl used when Python's HTTPS fails (default: curl")
    print("                                 on PATH; a set-but-invalid path is reported, not ignored)")
    print("  GET_HAIGGOH_NO_TRUSTSTORE=1    do not use the optional `truststore` package")
    print("  GET_HAIGGOH_REFRESH_TIMEOUT_S  per-plugin network timeout in seconds (default 5)")
    print()
    print("Exit status:")
    print("  0  everything known (and, for apply, every change landed)")
    print("  1  a plugin's published version could NOT be verified, or an apply step failed")
    print("  2  usage error")
    print()
    print("Examples:")
    print("  get-haiggoh upgrade")
    print("  get-haiggoh shims plan --on-collision=overwrite")
    print("  get-haiggoh apply --only waypoints")


def main(argv):
    # Handle --help flag
    if "--help" in argv:
        print_help()
        return 0

    usage = ("usage: get-haiggoh.py plan|dryrun|apply|upgrade|shims [plan|apply] [--only n1,n2] "
             "[--category NAME] [--on-collision skip|overwrite|prefix]")
    if not argv or argv[0] not in ("plan", "dryrun", "apply", "upgrade", "shims"):
        print(usage, file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    # dryrun is an alias for plan
    if cmd == "dryrun":
        cmd = "plan"
    mode = "plan"
    if cmd == "shims" and rest and rest[0] in ("plan", "apply"):
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
    return cmd_apply(only=only, category=category, policy=policy)  # apply and upgrade


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
