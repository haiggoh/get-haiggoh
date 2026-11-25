import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(REPO_ROOT, "bin", "get-haiggoh.py")


def run_cli(world, *args, extra_env=None):
    env = world.env()
    env.update(extra_env or {})
    return subprocess.run([sys.executable, CLI, *args], capture_output=True, text=True,
                          env=env, timeout=30, check=False)


@pytest.mark.parametrize("verb", ["apply", "upgrade"])
def test_apply_and_upgrade_both_install_shims(world, verb):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    r = run_cli(world, verb)
    assert r.returncode == 0, r.stderr
    assert "created" in r.stdout
    assert (world.bin / "waypoints").is_file()


def test_shims_plan_writes_nothing(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    r = run_cli(world, "shims", "plan")
    assert r.returncode == 0 and "would create" in r.stdout
    assert list(world.bin.iterdir()) == []


def test_bare_shims_is_a_dry_run(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    assert run_cli(world, "shims").returncode == 0
    assert list(world.bin.iterdir()) == []


def test_shims_apply_default_skips_a_collision(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    (world.bin / "waypoints").write_text("mine\n")
    r = run_cli(world, "shims", "apply")
    assert r.returncode == 0 and "SKIPPED" in r.stdout
    assert (world.bin / "waypoints").read_text() == "mine\n"


def test_shims_apply_overwrite_flag(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    (world.bin / "waypoints").write_text("mine\n")
    r = run_cli(world, "shims", "apply", "--on-collision=overwrite")
    assert r.returncode == 0 and "OVERWROTE" in r.stdout
    assert "haiggoh-shim" in (world.bin / "waypoints").read_text()
    assert len(list(world.backups.iterdir())) == 1


def test_only_limits_which_plugins_get_shims(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    world.plugin("cost-tracker", "0.9.1", ["cost-tracker"])
    run_cli(world, "shims", "apply", "--only", "waypoints")
    assert sorted(p.name for p in world.bin.iterdir()) == ["waypoints"]


def test_bad_policy_exits_2_with_usage_on_stderr(world):
    r = run_cli(world, "shims", "apply", "--on-collision=bogus")
    assert r.returncode == 2 and "on-collision" in r.stderr


def test_unknown_flag_exits_2(world):
    r = run_cli(world, "apply", "--frobnicate")
    assert r.returncode == 2 and "unrecognized" in r.stderr


def test_no_shims_env_disables_the_apply_step(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    r = run_cli(world, "apply", extra_env={"GET_HAIGGOH_NO_SHIMS": "1"})
    assert r.returncode == 0 and list(world.bin.iterdir()) == []


def test_help_documents_commands_flags_and_env(world):
    r = run_cli(world, "--help")
    assert r.returncode == 0
    for needle in ("upgrade", "shims", "--on-collision", "GET_HAIGGOH_SHIM_DIR",
                   "GET_HAIGGOH_NO_SHIMS", "GET_HAIGGOH_SHIM_BACKUP_DIR"):
        assert needle in r.stdout, needle


def path_edit_env(world):
    env = {"HOME": str(world.home), "ZDOTDIR": str(world.home), "SHELL": "/bin/zsh",
           "PATH": "/usr/bin:/bin"}
    return env


def run_cli_path(world, *args):
    env = world.env()
    env.pop("GET_HAIGGOH_NO_PATH_EDIT", None)
    env.update(path_edit_env(world))
    return subprocess.run([sys.executable, CLI, *args], capture_output=True, text=True,
                          env=env, timeout=30, check=False)


def test_shims_apply_puts_the_shim_dir_on_path(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    r = run_cli_path(world, "shims", "apply")
    assert r.returncode == 0, r.stderr
    assert "to your PATH in ~/.zprofile" in r.stdout
    assert "get-haiggoh PATH" in (world.home / ".zprofile").read_text()


def test_shims_path_reports_status_and_writes_nothing(world):
    r = run_cli_path(world, "shims", "path")
    assert r.returncode == 0, r.stderr
    assert "~/.zprofile" in r.stdout and "not added" in r.stdout
    assert not (world.home / ".zprofile").exists()


def test_shims_path_undo_removes_the_block(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    (world.home / ".zprofile").write_text("orig\n")
    run_cli_path(world, "shims", "apply")
    r = run_cli_path(world, "shims", "path", "--undo")
    assert r.returncode == 0 and "removed" in r.stdout
    assert (world.home / ".zprofile").read_text() == "orig\n"


def test_shims_path_unknown_flag_exits_2(world):
    r = run_cli_path(world, "shims", "path", "--bogus")
    assert r.returncode == 2 and "unrecognized" in r.stderr


def test_help_documents_path_and_bootstrap_env(world):
    r = run_cli(world, "--help")
    for needle in ("shims path", "--undo", "GET_HAIGGOH_NO_PATH_EDIT", "GET_HAIGGOH_TOOLS_DIR",
                   "GET_HAIGGOH_NO_UV_DOWNLOAD"):
        assert needle in r.stdout, needle
