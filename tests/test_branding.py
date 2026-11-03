#!/usr/bin/env python3
"""Branding (branding/credit-moments): the About mark 👨🏻‍💻 leads get-haiggoh's
credit-moment emits — update/shortcut notices, the CLI --help banner, the menu banner.

Usage: python3 tests/test_branding.py [-v]
"""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import get_haiggoh_core as c  # noqa: E402

MARK = "👨🏻‍💻"


class NudgeBrandingTests(unittest.TestCase):
    def test_update_nudge_first_line_exact(self):
        # exact pin — never loosened to a substring
        b = c.format_nudge(["measure-twice"], [])
        self.assertEqual(
            b.splitlines()[0],
            f'{MARK} get-haiggoh: new or updated haiggoh plugins available '
            '(ask me to "install all my haiggoh plugins" to sync):')

    def test_unverified_nudge_first_line_exact(self):
        b = c.format_nudge([], [], unverified=["cost-tracker"])
        self.assertTrue(
            b.startswith(f"{MARK} get-haiggoh: could not verify the published version of "),
            b.splitlines()[0])


class CliBrandingTests(unittest.TestCase):
    def test_help_banner_leads_with_mark(self):
        r = subprocess.run([sys.executable, str(ROOT / "bin" / "get-haiggoh.py"), "--help"],
                           capture_output=True, text=True, timeout=15)
        self.assertEqual(r.returncode, 0, r.stderr)
        line = next(ln for ln in r.stdout.splitlines() if "get-haiggoh CLI" in ln)
        self.assertTrue(line.startswith(f"{MARK} get-haiggoh CLI"), line)

    def test_menu_banner_is_title_plus_subtitle(self):
        # user amendment 2026-10-31: interactive menus restyle to a branded title
        # (emoji + name) with a subtitle, csl-style; the === rule is fixed-width so
        # the ZWJ mark needs no width correction
        r = subprocess.run([sys.executable, str(ROOT / "bin" / "get-haiggoh-menu")],
                           input="5\n", capture_output=True, text=True, timeout=15)
        lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
        self.assertEqual(lines[0], f"{MARK} Get Haiggoh")
        self.assertTrue(lines[1].strip().startswith("Install and keep every haiggoh plugin"),
                        lines[1])
        self.assertTrue(lines[2] and set(lines[2]) == {"="}, lines[2])


if __name__ == "__main__":
    unittest.main()
