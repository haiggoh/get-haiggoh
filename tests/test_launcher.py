import os
import pty
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(REPO_ROOT, "bin", "get-haiggoh")


def test_launcher_is_executable_and_declared():
    assert os.access(LAUNCHER, os.X_OK)
    with open(os.path.join(REPO_ROOT, "shortcuts")) as f:
        names = [line.split("#")[0].strip() for line in f if line.split("#")[0].strip()]
    assert names == ["get-haiggoh"]


def test_bare_run_on_a_terminal_opens_the_menu(world, tmp_path):
    fake = tmp_path / "fake-menu"
    fake.write_text("print('MENU-REACHED')\n")
    env = world.env()
    env["GET_HAIGGOH_MENU_SCRIPT"] = str(fake)
    master, slave = pty.openpty()
    try:
        r = subprocess.run([sys.executable, LAUNCHER], stdin=slave, capture_output=True,
                           text=True, env=env, timeout=15, check=False)
    finally:
        os.close(master)
        os.close(slave)
    assert r.returncode == 0 and "MENU-REACHED" in r.stdout


def test_bare_run_without_a_terminal_refuses_instead_of_crashing(world):
    r = subprocess.run([sys.executable, LAUNCHER], stdin=subprocess.DEVNULL, capture_output=True,
                       text=True, env=world.env(), timeout=15, check=False)
    assert r.returncode == 2
    assert "interactive" in r.stderr and "Traceback" not in r.stderr


def test_arguments_pass_through_to_the_cli(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    r = subprocess.run([sys.executable, LAUNCHER, "shims", "plan"], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, env=world.env(), timeout=15, check=False)
    assert r.returncode == 0 and "would create" in r.stdout


def test_help_passes_through(world):
    r = subprocess.run([sys.executable, LAUNCHER, "--help"], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, env=world.env(), timeout=15, check=False)
    assert r.returncode == 0 and "upgrade" in r.stdout
