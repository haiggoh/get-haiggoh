#!/usr/bin/env python3
"""Task 3 contract: brew_path resolution order.

Usage: python3 -m pytest tests/tui/test_routes.py -q
"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from get_haiggoh_tui import routes  # noqa: E402


class BrewPathTests(unittest.TestCase):
    def test_which_wins(self):
        with mock.patch.object(routes.shutil, "which", lambda name: "/custom/bin/brew"):
            self.assertEqual(routes.brew_path(), "/custom/bin/brew")

    def test_falls_back_to_standard_prefixes(self):
        with mock.patch.object(routes.shutil, "which", lambda name: None), \
             mock.patch.object(os.path, "isfile", lambda p: p == "/opt/homebrew/bin/brew"), \
             mock.patch.object(os, "access", lambda p, m: True):
            self.assertEqual(routes.brew_path(), "/opt/homebrew/bin/brew")

    def test_none_when_absent(self):
        with mock.patch.object(routes.shutil, "which", lambda name: None), \
             mock.patch.object(os.path, "isfile", lambda p: False):
            self.assertIsNone(routes.brew_path())


if __name__ == "__main__":
    unittest.main()
