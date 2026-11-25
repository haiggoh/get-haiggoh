import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO_ROOT, "hooks", "check-installed.py")


def run_hook(world, extra_env=None):
    env = world.env()
    env.update(extra_env or {})
    return subprocess.run([sys.executable, HOOK], input="{}", capture_output=True, text=True,
                          env=env, timeout=20, check=False)


def test_hook_creates_missing_shims_even_when_marketplace_is_unregistered(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    r = run_hook(world)
    assert r.returncode == 0
    assert (world.bin / "waypoints").is_file()
    out = json.loads(r.stdout)
    assert "👨🏻‍💻 get-haiggoh: added PATH shortcuts: waypoints" in out["hookSpecificOutput"]["additionalContext"]


def test_hook_never_touches_a_collision(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    (world.bin / "waypoints").write_text("mine\n")
    r = run_hook(world)
    assert r.returncode == 0 and r.stdout.strip() == ""
    assert (world.bin / "waypoints").read_text() == "mine\n"
    assert not world.backups.exists()


def test_hook_is_silent_once_shims_exist(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    run_hook(world)
    r = run_hook(world)
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_no_shims_env_disables_the_hook_step(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    r = run_hook(world, {"GET_HAIGGOH_NO_SHIMS": "1"})
    assert r.returncode == 0 and r.stdout.strip() == ""
    assert list(world.bin.iterdir()) == []


def test_hook_survives_a_corrupt_installed_record(world):
    world.record.write_text("{not json")
    r = run_hook(world)
    assert r.returncode == 0 and r.stdout.strip() == ""


def path_edit_env(world):
    """The fake machine as a stock Mac: zsh, startup files under the fake HOME, the shim
    dir NOT on PATH, and the conftest opt-out cleared (so only the fake HOME is edited)."""
    env = world.env()
    env.pop("GET_HAIGGOH_NO_PATH_EDIT", None)
    env.update(HOME=str(world.home), ZDOTDIR=str(world.home), SHELL="/bin/zsh",
               PATH="/usr/bin:/bin")
    return env


def test_hook_puts_the_shim_dir_on_path_once(world):
    world.plugin("get-haiggoh", "0.12.0", ["get-haiggoh"])
    env = path_edit_env(world)
    r = subprocess.run([sys.executable, HOOK], input="{}", capture_output=True, text=True,
                       env=env, timeout=30, check=False)
    assert r.returncode == 0, r.stderr
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "to your PATH in ~/.zprofile" in ctx
    assert "get-haiggoh PATH" in (world.home / ".zprofile").read_text()
    r2 = subprocess.run([sys.executable, HOOK], input="{}", capture_output=True, text=True,
                        env=env, timeout=30, check=False)
    assert r2.returncode == 0 and r2.stdout.strip() == "", "the block is added once, silently after"
