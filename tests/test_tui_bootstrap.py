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


def fake_python(tmp, name, major_minor):
    """An executable that answers the version probe like a real interpreter would."""
    f = Path(tmp) / name
    f.write_text(f'#!/bin/sh\necho "{major_minor}"\n')
    f.chmod(0o755)
    return f


def make_uv_tarball(tmp):
    """A release-shaped archive (uv-<arch>/uv) holding a fake uv; returns (path, sha256)."""
    import hashlib
    import io
    import tarfile
    tar = Path(tmp) / "uv-test.tar.gz"
    body = b'#!/bin/sh\necho "fake-uv"\n'
    with tarfile.open(tar, "w:gz") as t:
        info = tarfile.TarInfo("uv-test-arch/uv")
        info.size, info.mode = len(body), 0o755
        t.addfile(info, io.BytesIO(body))
    return tar, hashlib.sha256(tar.read_bytes()).hexdigest()


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
            # the venv path sits under a regular FILE, so venv creation itself fails —
            # a failure mode that survives the improved fallback chain (a stdlib venv +
            # its own pip would otherwise succeed and no longer exercise the fallback)
            blocker = tmp / "blocker"
            blocker.write_text("x")
            menu = tmp / "fake-menu"
            menu.write_text("import os\n"
                            "print('PLAIN-REACHED')\n"
                            "print('REASON=' + os.environ.get('GET_HAIGGOH_TUI_FALLBACK_REASON', ''))\n")
            env = base_env(tmp,
                           PATH=str(fakebin) + ":/usr/bin:/bin",
                           GET_HAIGGOH_TUI_VENV=str(blocker / "venv"),
                           GET_HAIGGOH_MENU_SCRIPT=str(menu))
            r = run_script(TUI, [], env)
            self.assertIn("TUI unavailable", r.stderr)
            self.assertIn("PLAIN-REACHED", r.stdout)
            self.assertEqual(r.returncode, 0)
            # colleague feedback 2026-11-25: the reason must ALSO reach the menu via the
            # env var, so the menu can show it under its banner (the stderr line scrolls away)
            reason = next(ln for ln in r.stdout.splitlines()
                          if ln.startswith("REASON="))[len("REASON="):]
            self.assertTrue(reason, "the fallback reason must reach the plain menu "
                                    "via GET_HAIGGOH_TUI_FALLBACK_REASON")
            self.assertIn(reason, r.stderr)  # same reason as the one-line stderr notice

    def test_req_change_rebuilds(self):
        # unit-level: venv_ok is False when the stamp differs, True when it matches;
        # ensure_venv rewrites the stamp (fake uv records its calls)
        mod = load_bootstrap()
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            venv = tmp / "venv"
            (venv / "bin").mkdir(parents=True)
            (venv / "bin" / "python").write_text("#!/bin/sh\n")
            (venv / "pyvenv.cfg").write_text("version_info = 3.12.4\n")
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

    def test_venv_on_python_below_floor_is_not_ok(self):
        # a venv built by macOS's /usr/bin/python3 (3.9) can never install the pins
        # (markdown-it-py 4 etc. need >=3.10), so a matching stamp must not save it
        mod = load_bootstrap()
        with tempfile.TemporaryDirectory() as d:
            venv = Path(d) / "venv"
            (venv / "bin").mkdir(parents=True)
            (venv / "bin" / "python").write_text("#!/bin/sh\n")
            (venv / ".req-sha").write_text(mod.req_sha())
            (venv / "pyvenv.cfg").write_text("home = /usr/bin\nversion = 3.9.6\n")
            self.assertFalse(mod.venv_ok(venv))
            (venv / "pyvenv.cfg").write_text("home = /x\nversion_info = 3.12.4\n")
            self.assertTrue(mod.venv_ok(venv))

    def test_find_base_python_skips_interpreters_below_floor(self):
        mod = load_bootstrap()
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            old, new = fake_python(tmp, "py39", "3 9"), fake_python(tmp, "py312", "3 12")
            self.assertIsNone(mod.find_base_python([str(old)]))
            self.assertEqual(mod.find_base_python([str(old), str(new)]), str(new))

    def test_old_venv_is_recreated_with_a_floor_python(self):
        # the sticky case: a first run on 3.9 left a venv behind; the next run must
        # rebuild it (uv venv --clear --python <floor>) instead of re-pipping into it
        mod = load_bootstrap()
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            venv = tmp / "venv"
            (venv / "bin").mkdir(parents=True)
            (venv / "bin" / "python").write_text("#!/bin/sh\n")
            (venv / "pyvenv.cfg").write_text("version = 3.9.6\n")
            fakebin = tmp / "fb"
            fakebin.mkdir()
            log = tmp / "uv.log"
            uv = fakebin / "uv"
            uv.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n'
                          f'case "$1" in venv) printf "version_info = 3.12.4\\n" > "{venv}/pyvenv.cfg";; esac\n')
            uv.chmod(0o755)
            old = os.environ["PATH"]
            os.environ["PATH"] = f"{fakebin}:{old}"
            try:
                mod.ensure_venv(str(venv))
            finally:
                os.environ["PATH"] = old
            calls = log.read_text().splitlines()
            self.assertTrue(calls[0].startswith("venv --clear --python"), calls)
            self.assertIn("pip install", calls[1])
            self.assertTrue(mod.venv_ok(venv))

    def test_no_floor_python_and_no_uv_names_the_fix(self):
        mod = load_bootstrap()
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            old = os.environ["PATH"]
            os.environ["PATH"] = str(tmp)  # no uv anywhere
            try:
                mod.find_base_python = lambda candidates=None: None
                mod.private_uv = lambda: None  # download unavailable too
                with self.assertRaises(RuntimeError) as cm:
                    mod.ensure_venv(str(tmp / "venv"))
            finally:
                os.environ["PATH"] = old
            msg = str(cm.exception)
            self.assertIn("3.10", msg)
            self.assertIn("no admin", msg)  # the route offered must not need admin or brew

    def test_fetch_uv_installs_verified_binary(self):
        mod = load_bootstrap()
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            tar, sha = make_uv_tarball(tmp)
            dest = tmp / "tools"
            path = mod.fetch_uv(str(dest), tar.as_uri(), sha)
            self.assertEqual(path, str(dest / "uv"))
            self.assertTrue(os.access(path, os.X_OK))
            r = subprocess.run([path], capture_output=True, text=True)
            self.assertEqual(r.stdout.strip(), "fake-uv")

    def test_fetch_uv_rejects_checksum_mismatch(self):
        mod = load_bootstrap()
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            tar, _ = make_uv_tarball(tmp)
            dest = tmp / "tools"
            with self.assertRaises(RuntimeError) as cm:
                mod.fetch_uv(str(dest), tar.as_uri(), "0" * 64)
            self.assertIn("sha256", str(cm.exception))
            self.assertFalse((dest / "uv").exists(), "a mismatched download must install nothing")

    def test_create_venv_uses_private_uv_when_nothing_else(self):
        # stock Mac: no Python >= 3.10, no uv on PATH, no brew -> the private pinned uv
        # builds the venv and fetches a managed Python itself
        mod = load_bootstrap()
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            venv = tmp / "venv"
            log = tmp / "uv.log"
            uv = tmp / "private-uv"
            uv.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n'
                          f'case "$1" in venv) /bin/mkdir -p "{venv}/bin"; : > "{venv}/bin/python";'
                          f' printf "version_info = 3.13.1\\n" > "{venv}/pyvenv.cfg";; esac\n')
            uv.chmod(0o755)
            old = os.environ["PATH"]
            os.environ["PATH"] = str(tmp / "empty")
            try:
                mod.find_base_python = lambda candidates=None: None
                mod.private_uv = lambda: str(uv)
                mod.ensure_venv(str(venv))
            finally:
                os.environ["PATH"] = old
            calls = log.read_text().splitlines()
            self.assertTrue(calls[0].startswith("venv --clear --python >=3.10"), calls)
            self.assertIn("pip install", calls[1])
            self.assertTrue(mod.venv_ok(venv))

    def test_no_download_env_names_the_fix(self):
        mod = load_bootstrap()
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            old = os.environ["PATH"]
            os.environ["PATH"] = str(tmp)
            os.environ["GET_HAIGGOH_NO_UV_DOWNLOAD"] = "1"
            try:
                mod.find_base_python = lambda candidates=None: None
                with self.assertRaises(RuntimeError) as cm:
                    mod.ensure_venv(str(tmp / "venv"))
            finally:
                os.environ["PATH"] = old
                del os.environ["GET_HAIGGOH_NO_UV_DOWNLOAD"]
            msg = str(cm.exception)
            self.assertIn("3.10", msg)
            self.assertIn("GET_HAIGGOH_NO_UV_DOWNLOAD", msg)

    def test_refuses_to_clear_a_non_venv_directory(self):
        mod = load_bootstrap()
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "precious"
            target.mkdir()
            (target / "notes.txt").write_text("keep me")
            with self.assertRaises(RuntimeError):
                mod.ensure_venv(str(target))
            self.assertEqual((target / "notes.txt").read_text(), "keep me")

    def test_broken_uv_on_path_falls_through_to_the_private_uv(self):
        # route 3 (the pinned private uv) exists for stock Macs with no local Python >= 3.10;
        # a uv on PATH whose `venv` fails must not block it (review 2026-11-25, finding 3)
        mod = load_bootstrap()
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            venv = tmp / "venv"
            log = tmp / "uv.log"
            fakebin = tmp / "fb"
            fakebin.mkdir()
            (fakebin / "uv").write_text("#!/bin/sh\nexit 1\n")
            (fakebin / "uv").chmod(0o755)
            private = tmp / "private-uv"
            private.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n'
                               f'case "$1" in venv) /bin/mkdir -p "{venv}/bin"; : > "{venv}/bin/python";'
                               f' printf "version_info = 3.13.1\\n" > "{venv}/pyvenv.cfg";; esac\n')
            private.chmod(0o755)
            old = os.environ["PATH"]
            os.environ["PATH"] = str(fakebin)
            try:
                mod.find_base_python = lambda candidates=None: None
                mod.private_uv = lambda: str(private)
                mod.ensure_venv(str(venv))
            finally:
                os.environ["PATH"] = old
            calls = log.read_text().splitlines()
            self.assertTrue(calls[0].startswith("venv --clear --python >=3.10"), calls)
            self.assertIn("pip install", calls[1])
            self.assertTrue(mod.venv_ok(venv))

    def test_ensure_venv_prefers_the_venvs_own_pip_over_a_failed_uv(self):
        # review 2026-11-25, finding 2: when `uv venv` fails but a stdlib venv was built,
        # the venv has its own working pip — the pip step must not re-select the failed uv
        mod = load_bootstrap()
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            venv = tmp / "venv"
            fakebin = tmp / "fb"
            fakebin.mkdir()
            uv = fakebin / "uv"
            uv.write_text('#!/bin/sh\ncase "$1" in venv) exit 1;; esac\nexit 0\n')
            uv.chmod(0o755)
            calls = []
            real_run = mod._run

            def recording_run(cmd, env=None):
                calls.append(list(cmd))
                if cmd[1:2] == ["-m"] and "venv" in cmd:  # stdlib venv route: fake success
                    (venv / "bin").mkdir(parents=True, exist_ok=True)
                    (venv / "bin" / "python").write_text("#!/bin/sh\n")
                    (venv / "bin" / "pip").write_text("#!/bin/sh\n")
                    (venv / "pyvenv.cfg").write_text("version_info = 3.12.4\n")
                    return
                if "pip" in cmd:
                    return
                raise RuntimeError(f"uv venv failed: {cmd}")

            mod._run = recording_run
            old = os.environ["PATH"]
            os.environ["PATH"] = f"{fakebin}:{old}"
            try:
                mod.ensure_venv(str(venv))
            finally:
                os.environ["PATH"] = old
                mod._run = real_run
            installs = [c for c in calls if "install" in c and "pip" in c]
            self.assertEqual(len(installs), 1, calls)
            self.assertEqual(installs[0][1:3], ["-m", "pip"], installs)  # venv's own pip, not uv
            self.assertTrue(mod.venv_ok(venv))

    def test_fetch_uv_download_has_a_timeout(self):
        # review 2026-11-25, finding 8: a stalled/black-holed connection must not hang the
        # bootstrap forever — the fallback-to-plain-menu design depends on failing fast
        mod = load_bootstrap()
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            tar, sha = make_uv_tarball(tmp)
            seen = []
            real_run = mod._run

            def recording_run(cmd, env=None):
                seen.append(list(cmd))
                return real_run(cmd, env=env)

            mod._run = recording_run
            try:
                mod.fetch_uv(str(tmp / "tools"), tar.as_uri(), sha)
            finally:
                mod._run = real_run
            curl_cmd = seen[0]
            self.assertIn("--max-time", curl_cmd, curl_cmd)
            self.assertIn("--connect-timeout", curl_cmd, curl_cmd)

    def test_py_version_rejects_a_nonzero_exit(self):
        # review 2026-11-25, finding 9: an interpreter that prints a version but exits
        # nonzero (a broken shim/wrapper) is not a usable base
        mod = load_bootstrap()
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad"
            bad.write_text('#!/bin/sh\necho "3 12"\nexit 1\n')
            bad.chmod(0o755)
            self.assertIsNone(mod.py_version(str(bad)))

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
