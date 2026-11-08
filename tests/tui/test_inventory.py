#!/usr/bin/env python3
"""Task 1 contract: brand_marks parsing, load_catalog shapes and coverage.

Usage: python3 -m pytest tests/tui/test_inventory.py -q   (or python3 tests/tui/test_inventory.py)
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from get_haiggoh_tui.inventory import Row, brand_marks, load_catalog  # noqa: E402

SPEC_TOOL_ORDER = ["claude-code-transcript-distiller", "human-shell",
                   "mac-claude-migration", "mac-iphone-backup-cloudsync"]


class BrandMarksTests(unittest.TestCase):
    def test_brand_marks_parses_pairs(self):
        md = (
            "## Marks (GitHub About, verbatim)\n\n"
            "waypoints 🧭 · free-agents 📡🦾 (lane-conditional: 📡 remote, 🦾 local) · "
            "cost-tracker 💸 (never the statusline, never the cap warning) · "
            "Claude-Code-Transcript-Distiller ⚗️\n"
        )
        marks = brand_marks(md)
        self.assertEqual(marks["free-agents"], "📡🦾")
        self.assertEqual(marks["cost-tracker"], "💸")
        self.assertEqual(marks["waypoints"], "🧭")
        # keys are lowercased so the repo-style name resolves the tool name
        self.assertEqual(marks["claude-code-transcript-distiller"], "⚗️")

    def test_brand_marks_ignores_non_marks_sections(self):
        md = "# branding\n\nSome prose about 👁️ never-brand rules.\n\n## Marks\n\nwaypoints 🧭\n"
        self.assertEqual(brand_marks(md), {"waypoints": "🧭"})


class LoadCatalogTests(unittest.TestCase):
    def test_tool_order_matches_spec(self):
        plugins, tools, extras = load_catalog(ROOT)
        self.assertEqual([t["name"] for t in tools], SPEC_TOOL_ORDER)

    def test_every_plugin_has_extras(self):
        plugins, tools, extras = load_catalog(ROOT)
        names = {p["name"] for p in plugins}
        self.assertEqual(names, set(extras.keys()),
                         f"marketplace {sorted(names ^ set(extras))} lack extras")

    def test_every_item_has_a_mark(self):
        plugins, tools, extras = load_catalog(ROOT)
        marks = brand_marks((ROOT / "docs" / "branding.md").read_text(encoding="utf-8"))
        for p in plugins:
            self.assertIn(p["name"], marks, f"no mark for plugin {p['name']}")
        for t in tools:
            self.assertIn(t["name"], marks, f"no mark for tool {t['name']}")

    def test_row_dataclass_fields(self):
        r = Row(name="x", section="plugin", mark="💸", description="d", adds="a",
                installed="1.0", latest="1.1", status="outdated", diagnostic=None,
                menu=None, tool=None)
        self.assertEqual(r.status, "outdated")


if __name__ == "__main__":
    unittest.main()
