#!/usr/bin/env python3
"""Task 2 contract: _compute(remote_versions=…) makes no network; skip semantics;
unverified never current; tool_status offline/brew; self row first.

Usage: python3 -m pytest tests/tui/test_status.py -q   (or python3 tests/tui/test_status.py)
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import get_haiggoh_core as c  # noqa: E402
from get_haiggoh_tui import status as st  # noqa: E402

WORLD_PLUGINS = [
    {"name": "get-haiggoh", "category": "meta", "description": "self",
     "source": {"source": "url", "url": "https://github.com/haiggoh/get-haiggoh.git"}},
    {"name": "waypoints", "category": "sessions", "description": "wp",
     "source": {"source": "url", "url": "https://github.com/haiggoh/waypoints.git"}},
    {"name": "cost-tracker", "category": "cost", "description": "ct",
     "source": {"source": "url", "url": "https://github.com/haiggoh/cost-tracker.git"}},
]

TOOL = {"name": "mac-claude-migration", "repo": "haiggoh/mac-claude-migration",
        "formula": "haiggoh/tap/mac-claude-migration", "version_cmd": None}


def _world(tmp_path, installed=None, skip=None, stamp=None):
    """Write a fake machine under tmp_path and return the env overrides that point at it."""
    mkt_dir = tmp_path / "marketplaces" / "haiggoh" / ".claude-plugin"
    mkt_dir.mkdir(parents=True)
    (mkt_dir / "marketplace.json").write_text(json.dumps({"plugins": WORLD_PLUGINS}))
    known = tmp_path / "known.json"
    known.write_text(json.dumps(
        {"haiggoh": {"installLocation": str(tmp_path / "marketplaces" / "haiggoh")}}))
    inst = tmp_path / "installed.json"
    inst.write_text(json.dumps({"plugins": {
        f"{n}@haiggoh": [{"version": v, "installPath": "/x"}]
        for n, v in (installed or {}).items()}}))
    skipf = tmp_path / "skip.json"
    skipf.write_text(json.dumps(skip or {}))
    stampf = tmp_path / "stamp.json"
    stampf.write_text(json.dumps(stamp or {}))
    return {
        "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": str(known),
        "GET_HAIGGOH_INSTALLED_PLUGINS_FILE": str(inst),
        "GET_HAIGGOH_SKIP_FILE": str(skipf),
        "GET_HAIGGOH_REFRESH_STAMP_FILE": str(stampf),
    }


def _boom(*a, **k):
    raise AssertionError("network/subprocess call attempted")


class ComputeTests(unittest.TestCase):
    def test_compute_with_remote_versions_makes_no_network(self):
        with tempfile.TemporaryDirectory() as d:
            env = _world(Path(d), installed={"get-haiggoh": "0.9.4", "waypoints": "0.14.3"})
            with mock.patch.dict(os.environ, env):
                cli = st.load_cli_module(ROOT)
                with mock.patch.object(c, "fetch_url", _boom), \
                     mock.patch.object(subprocess, "run", _boom):
                    _missing, _outdated, all_status = cli._compute(
                        remote_versions={"waypoints": "0.15.0", "get-haiggoh": "0.9.4"})
                by = {s["name"]: s for s in all_status}
                self.assertEqual(by["waypoints"]["status"], "outdated")
                self.assertEqual(by["get-haiggoh"]["status"], "current")
                self.assertNotIn("unverified", {s["status"] for s in all_status})

    def test_apply_skip_false_keeps_skipped_missing(self):
        with tempfile.TemporaryDirectory() as d:
            env = _world(Path(d), installed={"get-haiggoh": "0.9.4"}, skip={"waypoints": "install"})
            with mock.patch.dict(os.environ, env):
                cli = st.load_cli_module(ROOT)
                with mock.patch.object(c, "fetch_url", _boom):
                    _m, _o, all_status = cli._compute(apply_skip=False, remote_versions={})
                    by = {s["name"]: s for s in all_status}
                    self.assertEqual(by["waypoints"]["status"], "missing",
                                     "skipped missing item must still read missing, not unknown")
                    # default apply_skip=True keeps today's behaviour: filtered out of `missing`
                    missing, _o2, _a2 = cli._compute(remote_versions={})
                    self.assertNotIn("waypoints", missing)

    def test_unverified_never_current(self):
        with tempfile.TemporaryDirectory() as d:
            env = _world(Path(d), installed={"get-haiggoh": "0.9.4", "waypoints": "0.14.3"})
            with mock.patch.dict(os.environ, env):
                cli = st.load_cli_module(ROOT)

                def offline(*a, **k):
                    raise c.FetchError("offline", kind="network")
                with mock.patch.object(c, "fetch_url", offline):
                    _m, _o, all_status = cli._compute()
                by = {s["name"]: s for s in all_status}
                self.assertEqual(by["waypoints"]["status"], "unverified")
                self.assertIsNotNone(by["waypoints"]["diagnostic"])


class _R:
    def __init__(self, rc, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


class ToolStatusTests(unittest.TestCase):
    def test_tool_status_offline(self):
        def run_boom(*a, **k):
            raise FileNotFoundError("brew")

        def fetch_boom(*a, **k):
            raise OSError("offline")
        installed, latest, diag = st.tool_status(TOOL, run=run_boom, fetch=fetch_boom)
        self.assertIsNone(latest)
        self.assertIsNotNone(diag)
        self.assertIsNone(installed)

    def test_tool_status_brew_installed_and_latest(self):
        def run(args, **k):
            if args[:3] == ["brew", "list", "--versions"]:
                return _R(0, "mac-claude-migration 0.1.5\n")
            return _R(1, "", "Error: No such keg")

        def fetch(url, timeout):
            return json.dumps({"tag_name": "v0.1.5"}).encode()
        installed, latest, diag = st.tool_status(TOOL, run=run, fetch=fetch)
        self.assertEqual(installed, "0.1.5")
        self.assertEqual(latest, "0.1.5")
        self.assertIsNone(diag)

    def test_tool_status_outdated_via_version_cmd_without_brew(self):
        def run(args, **k):
            if args[:1] == ["brew"]:
                raise FileNotFoundError("brew")
            if args == ["cc-transcript", "--version"]:
                return _R(0, "0.8.4\n")
            return _R(1)

        def fetch(url, timeout):
            return json.dumps({"tag_name": "v0.9.0"}).encode()
        tool = dict(TOOL, name="claude-code-transcript-distiller",
                    repo="haiggoh/Claude-Code-Transcript-Distiller",
                    formula="haiggoh/tap/claude-code-transcript-distiller",
                    version_cmd=["cc-transcript", "--version"])
        installed, latest, diag = st.tool_status(tool, run=run, fetch=fetch)
        self.assertEqual(installed, "0.8.4")
        self.assertEqual(latest, "0.9.0")
        self.assertIsNone(diag)


class BuildRowsTests(unittest.TestCase):
    def test_self_row_first(self):
        with tempfile.TemporaryDirectory() as d:
            env = _world(Path(d), installed={"get-haiggoh": "0.9.4", "waypoints": "0.14.3"})
            with mock.patch.dict(os.environ, env):
                with mock.patch.object(c, "fetch_url", _boom), \
                     mock.patch.object(st, "tool_status", lambda tool: (None, "1.0.0", None)):
                    rows = st.build_rows(cached=False)
            self.assertEqual(rows[0].name, "get-haiggoh")
            self.assertEqual(rows[0].section, "plugin")
            names = [r.name for r in rows]
            self.assertIn("mac-claude-migration", names)  # tools appended after plugins
            self.assertLess(names.index("get-haiggoh"), names.index("waypoints"))


if __name__ == "__main__":
    unittest.main()
