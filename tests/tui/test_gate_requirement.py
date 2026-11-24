#!/usr/bin/env python3
"""Task 1 contract: with GET_HAIGGOH_REQUIRE_TEXTUAL=1 a TUI run must have textual
importable and zero skipped tests, or the session fails — so the ship gate can never
pass on silently skipped pilots.

Usage: pytest tests/tui/test_gate_requirement.py -q
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.tui.conftest import required_violation  # noqa: E402


class RequiredViolationTests(unittest.TestCase):
    def test_off_by_default(self):
        self.assertIsNone(required_violation({}, textual_ok=False, skipped=5))

    def test_required_but_textual_missing(self):
        msg = required_violation({"GET_HAIGGOH_REQUIRE_TEXTUAL": "1"}, textual_ok=False, skipped=0)
        self.assertIn("textual", msg)
        self.assertIn("GET_HAIGGOH_REQUIRE_TEXTUAL", msg)

    def test_required_and_skips_present(self):
        self.assertIn("3 skipped", required_violation({"GET_HAIGGOH_REQUIRE_TEXTUAL": "1"}, True, 3))

    def test_required_clean(self):
        self.assertIsNone(required_violation({"GET_HAIGGOH_REQUIRE_TEXTUAL": "1"}, True, 0))


if __name__ == "__main__":
    unittest.main()
