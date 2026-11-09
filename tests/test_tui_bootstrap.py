#!/usr/bin/env python3
"""Task 8 contract: get-haiggoh-tui bootstrap — --help is side-effect-free, unknown
flags exit 2, a SET-but-invalid venv override aborts naming it, a failed build falls
back to the plain menu with one stderr line, and a req change rebuilds.

Usage: python3 -m pytest tests/test_tui_bootstrap.py -q
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TUI = ROOT / "bin" / "get-haiggoh-tui"
OPENWIN = ROOT / "bin" / "get-haiggoh-open-window"


def load_bootstrap():
    # the script has no .py extension, so spec_from_file_location needs an explicit loader
    import importlib.machinery
    loader = importlib.machinery.SourceFileLoader("gh_tui_bootstrap", str(TUI))
    spec = importlib.util.spec_from_file_location("gh_tui_bootstrap", TUI, loader=loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_script(script, args, env):
    return subprocess.run([sys.executable, str(script), *args], capture_output=True,
                          text=True, env=env, timeout=60)


def base_env(tmp, **extra):
    env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(tmp),
    }
    env.update(extra)
    return env


class HelpTests(unittest.TestCase):
    def test_help_has_no_side_effects(self):
        with tempfile.TemporaryDirectory() as d:
            venv = Path(d) / "venv"
            env = base_env(d, GET_HAIGGOH_TUI_VENV=str(venv))
            r = run_script(TUI, ["--help"], env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("--check", r.stdout)
            self.assertFalse(venv.exists(), "--help must not create the venv")

    def test_unknown_flag_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            r = run_script(TUI, ["--bogus"], base_env(d))
            self.assertEqual(r.returncode, 2)
            self.assertIn("usage", r.stderr.lower())

    def test_open_window_help_and_unknown_flag(self):
        with tempfile.TemporaryDirectory() as d:
            r = run_script(OPENWIN, ["--help"], base_env(d))
            self.assertEqual(r.returncode, 0)
            self.assertIn("Terminal", r.stdout)
            r2 = run_script(OPENWIN, ["--bogus"], base_env(d))
            self.assertEqual(r2.returncode, 2)


class VenvOverrideTests(unittest.TestCase):
    def test_invalid_venv_override_aborts_naming_it(self):
        with tempfile.TemporaryDirectory() as d:
            notdir = Path(d) / "a-file"
            notdir.write_text("x")
            env = base_env(d, GET_HAIGGOH_TUI_VENV=str(notdir))
            r = run_script(TUI, ["--check"], env)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("GET_HAIGGOH_TUI_VENV", r.stderr)


class BootstrapTests(unittest.TestCase):
    def test_bootstrap_failure_falls_back_to_plain_menu(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fakebin = tmp / "bin"
            fakebin.mkdir()
            # a uv that always fails, and no working python3 either
            for name in ("uv", "python3"):
                f = fakebin / name
                f.write_text("#!/bin/sh\nexit 1\n")
                f.chmod(0o755)
            menu = tmp / "fake-menu"
            menu.write_text("print('PLAIN-REACHED')\n")
            env = base_env(tmp,
                           PATH=str(fakebin) + ":/usr/bin:/bin",
                           GET_HAIGGOH_TUI_VENV=str(tmp / "venv"),
                           GET_HAIGGOH_MENU_SCRIPT=str(menu))
            r = run_script(TUI, [], env)
            self.assertIn("TUI unavailable", r.stderr)
            self.assertIn("PLAIN-REACHED", r.stdout)
            self.assertEqual(r.returncode, 0)

    def test_req_change_rebuilds(self):
        # unit-level: venv_ok is False when the stamp differs, True when it matches;
        # ensure_venv rewrites the stamp (fake uv records its calls)
        mod = load_bootstrap()
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            venv = tmp / "venv"
            (venv / "bin").mkdir(parents=True)
            (venv / "bin" / "python").write_text("#!/bin/sh\n")
            (venv / ".req-sha").write_text("stale")
            self.assertFalse(mod.venv_ok(venv))
            (venv / ".req-sha").write_text(mod.req_sha())
            self.assertTrue(mod.venv_ok(venv))
            # ensure_venv with a fake uv on PATH records the build and rewrites the stamp
            fakebin = tmp / "bin2"
            fakebin.mkdir()
            log = tmp / "uv.log"
            uv = fakebin / "uv"
            uv.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\nexit 0\n')
            uv.chmod(0o755)
            (venv / ".req-sha").write_text("stale-again")
            env = dict(os.environ)
            env["PATH"] = f"{fakebin}:{env['PATH']}"
            old = os.environ.get("PATH")
            os.environ["PATH"] = env["PATH"]
            try:
                mod.ensure_venv(str(venv))
            finally:
                os.environ["PATH"] = old
            self.assertTrue(log.exists() and "pip" in log.read_text(), "uv pip install ran")
            self.assertEqual((venv / ".req-sha").read_text().strip(), mod.req_sha())
            self.assertTrue(mod.venv_ok(venv))

    def test_check_reports_state_and_changes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            venv = Path(d) / "venv"
            env = base_env(d, GET_HAIGGOH_TUI_VENV=str(venv))
            r = run_script(TUI, ["--check"], env)
            self.assertEqual(r.returncode, 1)  # venv missing -> not ok
            self.assertIn("not ok", r.stdout)
            self.assertFalse(venv.exists(), "--check must not build the venv")


if __name__ == "__main__":
    unittest.main()
