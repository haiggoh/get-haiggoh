#!/usr/bin/env python3
"""catalog-parity.py — verify the haiggoh marketplace catalog matches each repo's plugin.json.

For every entry in this repo's .claude-plugin/marketplace.json, compares its
description with <repos-root>/<name>/.claude-plugin/plugin.json. A missing checkout
is a FAILURE, not a skip.

Usage: catalog-parity.py [--repos-root DIR] [--help]
Exit 0 = all entries match · exit 1 = mismatches listed on stdout · exit 2 = bad args
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MARKETPLACE = os.path.join(os.path.dirname(HERE), ".claude-plugin", "marketplace.json")


def main(argv):
    ap = argparse.ArgumentParser(
        prog="catalog-parity.py",
        description="Check every marketplace.json description against the repo's plugin.json.")
    ap.add_argument("--repos-root", default=os.path.expanduser("~/ClaudeWorkspace"),
                    help="directory holding one checkout per plugin (default ~/ClaudeWorkspace)")
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
    if bad:
        print(f"{bad} entr{'y' if bad == 1 else 'ies'} differ or missing")
        return 1
    print(f"all {len(catalog)} catalog entries match their plugin.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
