import subprocess

import pytest

import get_haiggoh_shims as s


@pytest.mark.parametrize("name", ["waypoints", "get-haiggoh", "a.b_c", "x1"])
def test_valid_names(name):
    assert s.valid_name(name)


@pytest.mark.parametrize("name", ["", ".", "..", "../x", "a/b", "-rf", " x", "x y", "/abs"])
def test_invalid_names(name):
    assert not s.valid_name(name)


def test_read_shortcuts_returns_declared_real_executables(world):
    root = world.plugin("waypoints", "0.12.0", ["waypoints"])
    assert s.read_shortcuts(str(root)) == ["waypoints"]


def test_read_shortcuts_ignores_comments_blanks_duplicates_and_bad_names(world):
    root = world.plugin("p", "1.0.0", ["real"], declare=False)
    (root / "shortcuts").write_text("# header\n\nreal  # trailing\nreal\n../real\na/b\nmissing\n")
    assert s.read_shortcuts(str(root)) == ["real"]


def test_read_shortcuts_ignores_non_executable_target(world):
    root = world.plugin("p", "1.0.0", ["tool"], executable=False)
    assert s.read_shortcuts(str(root)) == []


def test_read_shortcuts_handles_missing_file_and_none(world):
    root = world.plugin("p", "1.0.0", ["tool"], declare=False)
    assert s.read_shortcuts(str(root)) == []
    assert s.read_shortcuts(None) == []


def test_wanted_lists_pairs_in_plugin_order(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    world.plugin("cost-tracker", "0.9.1", ["cost-tracker"])
    assert s.wanted(world.installed()) == [("cost-tracker", "cost-tracker"),
                                           ("waypoints", "waypoints")]


def _install_shim(world, plugin, command):
    path = world.bin / command
    path.write_text(s.render_shim(plugin, command))
    path.chmod(0o755)
    return path


def _run(shim, world, *args):
    return subprocess.run([str(shim), *args], capture_output=True, text=True,
                          env=world.env(), timeout=20)


def test_render_shim_has_shebang_and_marker_on_line_two():
    lines = s.render_shim("waypoints", "waypoints").splitlines()
    assert lines[0] == "#!/usr/bin/env bash"
    assert lines[1] == "# haiggoh-shim plugin=waypoints command=waypoints"


def test_shim_runs_installed_plugin_and_forwards_arguments(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    r = _run(_install_shim(world, "waypoints", "waypoints"), world, "list", "--gated")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "waypoints-0.12.0:waypoints:list --gated"


def test_shim_follows_a_version_bump_without_being_regenerated(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    shim = _install_shim(world, "waypoints", "waypoints")
    assert "0.12.0" in _run(shim, world).stdout
    world.plugin("waypoints", "0.13.0", ["waypoints"])  # new version dir + record now points at it
    assert "0.13.0" in _run(shim, world).stdout


def test_record_wins_over_a_higher_stale_cache_directory(world):
    world.plugin("get-haiggoh", "0.7.0", ["get-haiggoh"])
    stale = world.cache / "get-haiggoh" / "1.0.0" / "bin"
    stale.mkdir(parents=True)
    (stale / "get-haiggoh").write_text('#!/usr/bin/env bash\necho STALE\n')
    (stale / "get-haiggoh").chmod(0o755)
    r = _run(_install_shim(world, "get-haiggoh", "get-haiggoh"), world)
    assert "0.7.0" in r.stdout and "STALE" not in r.stdout


def test_fallback_picks_highest_numeric_version_when_record_missing(world):
    world.plugin("p", "1.9.0", ["p"])
    world.plugin("p", "1.10.0", ["p"])   # lexically smaller than 1.9.0, numerically larger
    world.record.write_text("{}")
    r = _run(_install_shim(world, "p", "p"), world)
    assert "1.10.0" in r.stdout, r.stdout + r.stderr


def test_shim_exits_127_with_a_hint_when_plugin_is_not_installed(world):
    r = _run(_install_shim(world, "ghost", "ghost"), world)
    assert r.returncode == 127
    assert "not installed" in r.stderr and "get-haiggoh apply" in r.stderr
