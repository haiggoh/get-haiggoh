#!/usr/bin/env python3
"""bin/catalog-parity.py contract: --help works, unknown flag exits 2, a repos-root
with missing checkouts exits 1 (failure, not skip), a fully-matching root exits 0.

Usage: python3 tests/test_catalog_parity.py [-v]
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "bin" / "catalog-parity.py"
APPROVED = json.loads(
    (Path.home() / ".claude" / "plans" / "2026-10-31-approved-plugin-descriptions.json")
    .read_text(encoding="utf-8"))["descriptions"]
CATALOG = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=30)


class CatalogParityTests(unittest.TestCase):
    def test_help(self):
        r = run("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("--repos-root", r.stdout)

    def test_unknown_flag_exits_2(self):
        r = run("--bogus")
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_missing_checkouts_are_failures_not_skips(self):
        # known-bad: empty root -> every catalog entry reported MISSING, exit 1
        with tempfile.TemporaryDirectory() as d:
            r = run("--repos-root", d)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(r.stdout.count("MISSING CHECKOUT:"), len(CATALOG["plugins"]))

    def test_matching_root_exits_0(self):
        # after-sync shape: one fake checkout per catalog entry carrying the approved text
        with tempfile.TemporaryDirectory() as d:
            for entry in CATALOG["plugins"]:
                pj = Path(d) / entry["name"] / ".claude-plugin"
                pj.mkdir(parents=True)
                (pj / "plugin.json").write_text(json.dumps(
                    {"name": entry["name"], "description": APPROVED[entry["name"]]}),
                    encoding="utf-8")
            r = run("--repos-root", d)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("all 16 catalog entries match", r.stdout)

    def test_mismatch_is_listed_and_fails(self):
        with tempfile.TemporaryDirectory() as d:
            for entry in CATALOG["plugins"]:
                pj = Path(d) / entry["name"] / ".claude-plugin"
                pj.mkdir(parents=True)
                desc = APPROVED[entry["name"]]
                if entry["name"] == "waypoints":
                    desc = "stale text"
                (pj / "plugin.json").write_text(json.dumps(
                    {"name": entry["name"], "description": desc}), encoding="utf-8")
            r = run("--repos-root", d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("MISMATCH: waypoints", r.stdout)


if __name__ == "__main__":
    unittest.main()
