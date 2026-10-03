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
