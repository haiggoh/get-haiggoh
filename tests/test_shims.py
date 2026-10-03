import os
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


def _apply(world, policy="skip"):
    acts = s.plan_shims(world.installed(), policy=policy, directory=str(world.bin))
    for a in acts:
        s.apply_action(a)
    return acts


def test_create_writes_an_executable_shim_that_runs(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    acts = _apply(world)
    assert [a["action"] for a in acts] == ["create"]
    shim = world.bin / "waypoints"
    assert os.access(shim, os.X_OK) and s.is_our_shim(str(shim))
    assert "waypoints-0.12.0" in _run(shim, world).stdout


def test_second_apply_is_a_noop(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    _apply(world)
    before = (world.bin / "waypoints").stat().st_mtime_ns
    acts = _apply(world)
    assert [a["action"] for a in acts] == ["noop"]
    assert (world.bin / "waypoints").stat().st_mtime_ns == before


def test_stale_shim_is_refreshed(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    _apply(world)
    shim = world.bin / "waypoints"
    shim.write_text(shim.read_text() + "# drift\n")
    assert [a["action"] for a in _apply(world)] == ["refresh"]
    assert "drift" not in shim.read_text()


def test_skip_leaves_a_foreign_symlink_untouched_and_explains(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    agy = world.home / "agy-waypoints"
    agy.write_text("agy\n")
    (world.bin / "waypoints").symlink_to(agy)
    acts = _apply(world, "skip")
    assert acts[0]["action"] == "skip" and "symlink" in acts[0]["detail"]
    assert (world.bin / "waypoints").is_symlink()
    report = s.format_report(acts, str(world.bin), applied=True)
    assert "SKIPPED" in report
    assert "--on-collision=overwrite" in report and "--on-collision=prefix" in report


def test_overwrite_replaces_the_link_without_writing_through_it(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    agy = world.home / "agy-waypoints"
    agy.write_text("#!/bin/sh\necho agy\n")
    (world.bin / "waypoints").symlink_to(agy)
    acts = _apply(world, "overwrite")
    link = world.bin / "waypoints"
    assert acts[0]["action"] == "overwrite"
    assert not link.is_symlink() and s.is_our_shim(str(link))
    assert agy.read_text() == "#!/bin/sh\necho agy\n"          # write-through would clobber this
    backups = list(world.backups.iterdir())
    assert len(backups) == 1 and backups[0].read_text().strip() == str(agy)
    assert acts[0]["backup"] == str(backups[0])


def test_overwrite_of_a_regular_file_keeps_an_identical_backup(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    (world.bin / "waypoints").write_text("#!/bin/sh\necho mine\n")
    _apply(world, "overwrite")
    backups = list(world.backups.iterdir())
    assert len(backups) == 1 and backups[0].read_text() == "#!/bin/sh\necho mine\n"


def test_prefix_installs_haiggoh_name_and_leaves_the_original(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    (world.bin / "waypoints").write_text("mine\n")
    acts = _apply(world, "prefix")
    assert acts[0]["action"] == "create" and acts[0]["name"] == "haiggoh-waypoints"
    assert (world.bin / "waypoints").read_text() == "mine\n"
    assert "waypoints-0.12.0" in _run(world.bin / "haiggoh-waypoints", world).stdout


def test_prefix_skips_when_the_prefixed_name_is_taken_too(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    (world.bin / "waypoints").write_text("mine\n")
    (world.bin / "haiggoh-waypoints").write_text("also mine\n")
    acts = _apply(world, "prefix")
    assert acts[0]["action"] == "skip"
    assert (world.bin / "haiggoh-waypoints").read_text() == "also mine\n"


def test_directory_in_the_way_is_skipped_even_under_overwrite(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    (world.bin / "waypoints").mkdir()
    acts = _apply(world, "overwrite")
    assert acts[0]["action"] == "skip" and (world.bin / "waypoints").is_dir()


def test_two_plugins_declaring_one_name_second_is_skipped(world):
    world.plugin("a-plugin", "1.0.0", ["tool"])
    world.plugin("b-plugin", "1.0.0", ["tool"])
    acts = _apply(world)
    assert [a["action"] for a in acts] == ["create", "skip"]
    assert "a-plugin" in acts[1]["detail"]


def test_is_our_shim_reads_bytes_not_lines(world):
    big = world.bin / "joyia"
    big.write_bytes(b"\x00" * 5_000_000)   # a huge binary with no newline
    assert s.is_our_shim(str(big)) is False


def test_unknown_policy_is_rejected(world):
    with pytest.raises(ValueError):
        s.plan_shims(world.installed(), policy="nuke", directory=str(world.bin))


def test_create_does_not_clobber_a_file_that_appears_after_planning(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    acts = s.plan_shims(world.installed(), policy="skip", directory=str(world.bin))
    assert acts[0]["action"] == "create"
    (world.bin / "waypoints").write_text("USER FILE\n")      # another writer wins the race
    s.apply_action(acts[0])
    assert (world.bin / "waypoints").read_text() == "USER FILE\n"
    assert acts[0]["action"] == "skip" and "appeared" in acts[0]["detail"]
    assert list(world.bin.glob("*tmp*")) == []


def test_create_does_not_follow_a_dangling_symlink_planted_after_planning(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    acts = s.plan_shims(world.installed(), policy="skip", directory=str(world.bin))
    (world.bin / "waypoints").symlink_to(world.home / "nowhere")
    s.apply_action(acts[0])
    assert (world.bin / "waypoints").is_symlink() and acts[0]["action"] == "skip"
    assert not (world.home / "nowhere").exists()


def test_refresh_does_not_clobber_a_foreign_file_that_replaced_our_shim(world):
    world.plugin("waypoints", "0.12.0", ["waypoints"])
    _apply(world)
    shim = world.bin / "waypoints"
    shim.write_text(shim.read_text() + "# drift\n")
    acts = s.plan_shims(world.installed(), policy="skip", directory=str(world.bin))
    assert acts[0]["action"] == "refresh"
    shim.write_text("USER FILE\n")                            # swapped in after planning
    s.apply_action(acts[0])
    assert shim.read_text() == "USER FILE\n" and acts[0]["action"] == "skip"
    assert not world.backups.exists()
