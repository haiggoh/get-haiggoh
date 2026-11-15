#!/usr/bin/env python3
"""catalog-parity.py — verify the haiggoh marketplace catalog matches each repo's plugin.json,
and that the TUI catalog (catalog/) and brand marks do not lag the marketplace.

For every entry in <repo-root>/.claude-plugin/marketplace.json, compares its
description with <repos-root>/<name>/.claude-plugin/plugin.json. A missing checkout
is a FAILURE, not a skip. Also checks, from <repo-root>: every marketplace plugin has
a catalog/plugin-extras.json entry, and every plugin + catalog/related-tools.json name
resolves a mark in docs/branding.md § Marks.

Usage: catalog-parity.py [--repos-root DIR] [--repo-root DIR] [--help]
Exit 0 = all checks pass · exit 1 = problems listed on stdout · exit 2 = bad args
"""
import argparse
import json
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
MARKETPLACE = os.path.join(REPO, ".claude-plugin", "marketplace.json")


def check_catalog(repo_root, bad):
    """TUI catalog coverage: extras keys == marketplace names; every name has a mark."""
    sys.path.insert(0, REPO)  # import the parser from this repo, read DATA from repo_root
    from get_haiggoh_tui.inventory import brand_marks, load_catalog
    plugins, tools, extras = load_catalog(Path(repo_root))
    names = {p["name"] for p in plugins}
    for missing in sorted(names - set(extras)):
        print(f"MISSING EXTRA: {missing} — no entry in catalog/plugin-extras.json")
        bad += 1
    for stale in sorted(set(extras) - names):
        print(f"STALE EXTRA: {stale} — not in marketplace.json")
        bad += 1
    with open(os.path.join(repo_root, "docs", "branding.md"), encoding="utf-8") as f:
        marks = brand_marks(f.read())
    for n in sorted(names | {t["name"] for t in tools}):
        if n not in marks:
            print(f"NO MARK: {n} — not in docs/branding.md § Marks")
            bad += 1
    return bad


def main(argv):
    ap = argparse.ArgumentParser(
        prog="catalog-parity.py",
        description="Check marketplace descriptions against the repos' plugin.json, plus TUI catalog coverage.")
    ap.add_argument("--repos-root", default=os.path.expanduser("~/ClaudeWorkspace"),
                    help="directory holding one checkout per plugin (default ~/ClaudeWorkspace)")
    ap.add_argument("--repo-root", default=REPO,
                    help="repo root holding .claude-plugin/, catalog/, docs/branding.md (default: this repo)")
    args = ap.parse_args(argv)  # unknown flag -> usage on stderr, exit 2

    with open(MARKETPLACE, encoding="utf-8") as f:
        catalog = json.load(f)["plugins"]

    bad = 0
    for entry in catalog:
        name = entry["name"]
        pj = os.path.join(args.repos_root, name, ".claude-plugin", "plugin.json")
        if not os.path.exists(pj):
            print(f"MISSING CHECKOUT: {name} — no plugin.json at {pj}")
            bad += 1
            continue
        with open(pj, encoding="utf-8") as f:
            desc = json.load(f)["description"]
        if desc != entry.get("description"):
            print(f"MISMATCH: {name}")
            bad += 1
    bad = check_catalog(args.repo_root, bad)
    if bad:
        print(f"{bad} entr{'y' if bad == 1 else 'ies'} differ or missing")
        return 1
    print(f"all {len(catalog)} catalog entries match their plugin.json; extras and marks complete")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
