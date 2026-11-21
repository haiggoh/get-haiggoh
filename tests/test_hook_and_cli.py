import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO_ROOT, "hooks", "check-installed.py")
CLI = os.path.join(REPO_ROOT, "bin", "get-haiggoh.py")


def _run(env_extra=None, stdin_data=""):
    env = os.environ.copy()
    env.update(env_extra or {})
    return subprocess.run([sys.executable, HOOK], input=stdin_data, capture_output=True,
                           text=True, env=env, timeout=10)


def _run_cli(args, env_extra=None):
    env = os.environ.copy()
    env.update(env_extra or {})
    return subprocess.run([sys.executable, CLI] + args, capture_output=True, text=True,
                           env=env, timeout=10)


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def test_claude_startup_reports_only_provably_missing_scripts_without_arguments(tmp_path):
    import shlex
    config = tmp_path / "config with space"
    config.mkdir()
    healthy = tmp_path / "healthy.py"
    healthy.write_text("pass\n")
    missing = tmp_path / "missing script.py"
    direct = tmp_path / "missing-direct.sh"
    settings = config / "settings.json"
    document = {"hooks": {"Stop": [{"hooks": [
        {"type": "command", "command": f"python3 {shlex.quote(str(missing))} --secret PRIVATE_TOKEN"},
        {"type": "command", "command": f"python3 {shlex.quote(str(healthy))}"},
        {"type": "command", "command": f"python3 {shlex.quote(str(tmp_path / 'uncertain.py'))} | echo x"},
        {"type": "command", "enabled": False, "command": f"python3 {shlex.quote(str(tmp_path / 'disabled.py'))}"},
        {"type": "command", "command": shlex.quote(str(direct))},
    ]}]}}
    settings.write_text(json.dumps(document))
    before = settings.read_bytes()
    r = _run({"CLAUDE_CONFIG_DIR": str(config), "GET_HAIGGOH_NO_SHIMS": "1",
              "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": str(tmp_path / "absent")}, "{}")
    assert r.returncode == 0
    notice = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "Stop" in notice and str(missing) in notice and str(direct) in notice
    assert "PRIVATE_TOKEN" not in notice and "--secret" not in notice
    assert str(healthy) not in notice and "uncertain.py" not in notice and "disabled.py" not in notice
    assert settings.read_bytes() == before


def test_claude_startup_disabled_and_healthy_are_silent(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"disableAllHooks": True, "hooks": {"Stop": [{"hooks": [
        {"type": "command", "command": "python3 /missing.py"}]}]}}))
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path), "GET_HAIGGOH_NO_SHIMS": "1",
           "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": str(tmp_path / "absent")}
    assert _run(env, "{}").stdout == ""
    settings.write_text(json.dumps({"hooks": {}}))
    assert _run(env, "{}").stdout == ""


def test_claude_startup_expands_only_unquoted_tilde_and_safe_home(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    settings = tmp_path / "settings.json"
    commands = ["python3 ~/missing.py", "~/direct.sh", "python3 '~/quoted.py'",
                'python3 "~/double.py"', 'python3 "$HOME/home.py"',
                "python3 '$HOME/literal.py'"]
    settings.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [
        {"type": "command", "command": c} for c in commands]}]}}))
    r = _run({"HOME": str(home), "CLAUDE_CONFIG_DIR": str(tmp_path),
              "GET_HAIGGOH_NO_SHIMS": "1", "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": str(tmp_path / "absent")}, "{}")
    notice = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert str(home / "missing.py") in notice and str(home / "direct.sh") in notice
    assert str(home / "home.py") in notice
    assert "quoted.py" not in notice and "double.py" not in notice and "literal.py" not in notice


def test_claude_startup_diagnoses_malformed_or_unreadable_settings(tmp_path):
    settings = tmp_path / "settings.json"
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path), "GET_HAIGGOH_NO_SHIMS": "1",
           "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": str(tmp_path / "absent")}
    settings.write_text("{invalid PRIVATE_TOKEN")
    r = _run(env, "{}")
    assert "settings.json" in r.stdout and "PRIVATE_TOKEN" not in r.stdout
    settings.unlink()
    settings.mkdir()
    r = _run(env, "{}")
    assert "settings.json" in r.stdout


def test_claude_startup_reports_invalid_config_dir_but_missing_settings_is_quiet(tmp_path):
    missing = tmp_path / "missing"
    file_path = tmp_path / "file"
    file_path.write_text("not a directory")
    env = {"GET_HAIGGOH_NO_SHIMS": "1", "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": str(tmp_path / "absent")}
    for path in (missing, file_path):
        r = _run({**env, "CLAUDE_CONFIG_DIR": str(path)}, "{}")
        assert r.returncode == 0 and "CLAUDE_CONFIG_DIR" in r.stdout
    r = _run({**env, "CLAUDE_CONFIG_DIR": str(tmp_path)}, "{}")
    assert r.returncode == 0 and r.stdout == ""


def test_hook_prints_nothing_when_marketplace_not_registered(tmp_path):
    env = {
        "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": str(tmp_path / "nope.json"),
        "GET_HAIGGOH_INSTALLED_PLUGINS_FILE": str(tmp_path / "nope2.json"),
        "GET_HAIGGOH_SKIP_FILE": str(tmp_path / "skip.json"),
        "GET_HAIGGOH_REFRESH_STAMP_FILE": str(tmp_path / "stamp.json"),
        "GET_HAIGGOH_SELF_NAME": "get-haiggoh",
    }
    r = _run(env)
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_hook_prints_nudge_when_a_catalog_plugin_is_missing(tmp_path):
    known_path = str(tmp_path / "known_marketplaces.json")
    marketplace_dir = tmp_path / "marketplaces" / "haiggoh" / ".claude-plugin"
    marketplace_path = marketplace_dir / "marketplace.json"
    installed_path = str(tmp_path / "installed_plugins.json")

    _write_json(known_path, {"haiggoh": {"installLocation": str(tmp_path / "marketplaces" / "haiggoh")}})
    _write_json(str(marketplace_path), {"plugins": [
        {"name": "get-haiggoh", "source": {"source": "url", "url": "https://github.com/haiggoh/get-haiggoh.git"}},
        {"name": "measure-twice", "source": {"source": "url", "url": "https://github.com/haiggoh/measure-twice.git"}},
    ]})
    _write_json(installed_path, {"plugins": {}})

    env = {
        "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": known_path,
        "GET_HAIGGOH_INSTALLED_PLUGINS_FILE": installed_path,
        "GET_HAIGGOH_SKIP_FILE": str(tmp_path / "skip.json"),
        "GET_HAIGGOH_REFRESH_STAMP_FILE": str(tmp_path / "stamp.json"),
        "GET_HAIGGOH_SELF_NAME": "get-haiggoh",
        "GET_HAIGGOH_SKIP_NETWORK_REFRESH": "1",  # test hook: never shell out in tests
    }
    r = _run(env)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert "measure-twice" in out["hookSpecificOutput"]["additionalContext"]


def test_hook_never_shells_out_to_git_ls_remote(tmp_path):
    """Regression test: the hook must not do per-session outdated-detection network calls.
    Fixed 2026-07-17 (was an unthrottled `git ls-remote` per catalog entry, every session)."""
    known_path = str(tmp_path / "known_marketplaces.json")
    marketplace_dir = tmp_path / "marketplaces" / "haiggoh" / ".claude-plugin"
    marketplace_path = marketplace_dir / "marketplace.json"
    installed_path = str(tmp_path / "installed_plugins.json")

    _write_json(known_path, {"haiggoh": {"installLocation": str(tmp_path / "marketplaces" / "haiggoh")}})
    _write_json(str(marketplace_path), {"plugins": [
        {"name": "get-haiggoh", "source": {"source": "url", "url": "https://github.com/haiggoh/get-haiggoh.git"}},
        {"name": "measure-twice", "source": {"source": "url", "url": "https://github.com/haiggoh/measure-twice.git"}},
    ]})
    _write_json(installed_path, {"plugins": {"measure-twice@haiggoh": [{"gitCommitSha": "deadbeef"}]}})

    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir()
    called = tmp_path / "git-was-called"
    fake_git = fake_bin / "git"
    # `: >` is a shell builtin: PATH holds only fake_bin, so an external `touch` would not be found
    fake_git.write_text(f"#!/bin/sh\n: > '{called}'\n")
    fake_git.chmod(0o755)

    env = {
        "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": known_path,
        "GET_HAIGGOH_INSTALLED_PLUGINS_FILE": installed_path,
        "GET_HAIGGOH_SKIP_FILE": str(tmp_path / "skip.json"),
        "GET_HAIGGOH_REFRESH_STAMP_FILE": str(tmp_path / "stamp.json"),
        "GET_HAIGGOH_SELF_NAME": "get-haiggoh",
        "GET_HAIGGOH_SKIP_NETWORK_REFRESH": "1",
        # The hook now compares plugin VERSIONS fetched over HTTP, not shas from git. Without this
        # it makes a real manifest request (~20s offline), which blew the 10s test timeout.
        "GET_HAIGGOH_SKIP_REMOTE_VERSION_CHECK": "1",
        # A fake `git` that records being called. An absent git is not a usable tripwire: the hook
        # swallows every exception and exits 0, so a failed call looks exactly like no call.
        "PATH": str(fake_bin),
    }
    r = _run(env)
    assert r.returncode == 0
    assert r.stdout.strip() == ""  # measure-twice is installed and not missing -- nothing to nudge
    assert not called.exists(), "the hook invoked git"


def test_hook_prints_nothing_when_stdin_is_malformed(tmp_path):
    env = {
        "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": str(tmp_path / "nope.json"),
        "GET_HAIGGOH_INSTALLED_PLUGINS_FILE": str(tmp_path / "nope2.json"),
    }
    r = _run(env, stdin_data="{not json")
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_hook_respects_refresh_throttle_stamp(tmp_path):
    stamp_path = str(tmp_path / "stamp.json")
    with open(stamp_path, "w") as f:
        json.dump({"date": "2026-07-16"}, f)
    env = {
        "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": str(tmp_path / "nope.json"),
        "GET_HAIGGOH_INSTALLED_PLUGINS_FILE": str(tmp_path / "nope2.json"),
        "GET_HAIGGOH_REFRESH_STAMP_FILE": stamp_path,
        "GET_HAIGGOH_TODAY": "2026-07-16",
    }
    r = _run(env)
    assert r.returncode == 0  # unregistered marketplace short-circuits before refresh either way; throttle path exercised by no crash + exit 0


def test_cli_plan_lists_missing_plugin(tmp_path):
    known_path = str(tmp_path / "known_marketplaces.json")
    marketplace_dir = tmp_path / "marketplaces" / "haiggoh" / ".claude-plugin"
    marketplace_path = marketplace_dir / "marketplace.json"
    installed_path = str(tmp_path / "installed_plugins.json")

    _write_json(known_path, {"haiggoh": {"installLocation": str(tmp_path / "marketplaces" / "haiggoh")}})
    _write_json(str(marketplace_path), {"plugins": [
        {"name": "get-haiggoh", "source": {"source": "url", "url": "https://github.com/haiggoh/get-haiggoh.git"}},
        {"name": "measure-twice", "source": {"source": "url", "url": "https://github.com/haiggoh/measure-twice.git"}},
    ]})
    _write_json(installed_path, {"plugins": {}})

    env = {
        "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": known_path,
        "GET_HAIGGOH_INSTALLED_PLUGINS_FILE": installed_path,
        "GET_HAIGGOH_SKIP_FILE": str(tmp_path / "skip.json"),
        "GET_HAIGGOH_SELF_NAME": "get-haiggoh",
        "GET_HAIGGOH_SKIP_REMOTE_SHA_CHECK": "1",
    }
    r = _run_cli(["plan"], env)
    assert r.returncode == 0
    assert "measure-twice" in r.stdout


def test_cli_plan_reports_nothing_to_do(tmp_path):
    known_path = str(tmp_path / "known_marketplaces.json")
    marketplace_dir = tmp_path / "marketplaces" / "haiggoh" / ".claude-plugin"
    marketplace_path = marketplace_dir / "marketplace.json"
    installed_path = str(tmp_path / "installed_plugins.json")

    _write_json(known_path, {"haiggoh": {"installLocation": str(tmp_path / "marketplaces" / "haiggoh")}})
    _write_json(str(marketplace_path), {"plugins": [
        {"name": "get-haiggoh", "source": {"source": "url", "url": "https://github.com/haiggoh/get-haiggoh.git"}},
    ]})
    _write_json(installed_path, {"plugins": {}})

    env = {
        "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": known_path,
        "GET_HAIGGOH_INSTALLED_PLUGINS_FILE": installed_path,
        "GET_HAIGGOH_SKIP_FILE": str(tmp_path / "skip.json"),
        "GET_HAIGGOH_SELF_NAME": "get-haiggoh",
        "GET_HAIGGOH_SKIP_REMOTE_SHA_CHECK": "1",
    }
    r = _run_cli(["plan"], env)
    assert r.returncode == 0
    # New output says "All haiggoh plugins are current." instead of "nothing to do"
    assert "all haiggoh plugins are current" in r.stdout.lower()


def _selection_env(tmp_path):
    known_path = str(tmp_path / "known_marketplaces.json")
    marketplace_dir = tmp_path / "marketplaces" / "haiggoh" / ".claude-plugin"
    marketplace_path = marketplace_dir / "marketplace.json"
    installed_path = str(tmp_path / "installed_plugins.json")

    _write_json(known_path, {"haiggoh": {"installLocation": str(tmp_path / "marketplaces" / "haiggoh")}})
    _write_json(str(marketplace_path), {"plugins": [
        {"name": "get-haiggoh", "category": "meta",
         "source": {"source": "url", "url": "https://github.com/haiggoh/get-haiggoh.git"}},
        {"name": "measure-twice", "category": "safety",
         "source": {"source": "url", "url": "https://github.com/haiggoh/measure-twice.git"}},
        {"name": "waypoints", "category": "sessions",
         "source": {"source": "url", "url": "https://github.com/haiggoh/waypoints.git"}},
    ]})
    _write_json(installed_path, {"plugins": {}})
    return {
        "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": known_path,
        "GET_HAIGGOH_INSTALLED_PLUGINS_FILE": installed_path,
        "GET_HAIGGOH_SKIP_FILE": str(tmp_path / "skip.json"),
        "GET_HAIGGOH_SELF_NAME": "get-haiggoh",
        "GET_HAIGGOH_SKIP_REMOTE_SHA_CHECK": "1",
    }


def test_cli_plan_only_restricts_to_named_plugins(tmp_path):
    env = _selection_env(tmp_path)
    r = _run_cli(["plan", "--only", "waypoints"], env)
    assert r.returncode == 0
    assert "waypoints" in r.stdout
    assert "measure-twice" not in r.stdout


def test_cli_plan_category_restricts_to_matching_plugins(tmp_path):
    env = _selection_env(tmp_path)
    r = _run_cli(["plan", "--category", "safety"], env)
    assert r.returncode == 0
    assert "measure-twice" in r.stdout
    assert "waypoints" not in r.stdout


def test_cli_unrecognized_flag_errors_instead_of_running_unfiltered(tmp_path):
    env = _selection_env(tmp_path)
    r = _run_cli(["plan", "--bogus", "x"], env)
    assert r.returncode == 2
    assert "unrecognized" in r.stderr.lower()
    # must NOT have silently fallen through to an unfiltered plan
    assert "measure-twice" not in r.stdout and "waypoints" not in r.stdout


def _load_cli(monkeypatch, env):
    """Import bin/get-haiggoh.py as a module with `env` applied, so cmd_apply can be called
    directly and its subprocess calls intercepted."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("get_haiggoh_cli", CLI)
    mod = importlib.util.module_from_spec(spec)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    spec.loader.exec_module(mod)
    return mod


class _Ok:
    returncode = 0
    stderr = ""


def test_cli_apply_only_updates_just_the_named_plugin(monkeypatch, tmp_path):
    env = _selection_env(tmp_path)
    calls = []
    mod = _load_cli(monkeypatch, env)
    installed_path = env["GET_HAIGGOH_INSTALLED_PLUGINS_FILE"]

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        # a real `claude plugin install` records the plugin; the outcome check reads that back
        _write_json(installed_path,
                    {"plugins": {"waypoints@haiggoh": [{"version": "0.5.1"}]}})
        return _Ok()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    rc = mod.cmd_apply(only=["waypoints"])
    assert rc == 0
    updated_names = {c[3].split("@")[0] for c in calls if c[1] == "plugin"}
    assert updated_names == {"waypoints"}


def test_cli_apply_reports_not_applied_when_the_version_does_not_move(
        monkeypatch, capsys, tmp_path):
    """`claude plugin update` exits 0 for "the clone succeeded". The install path is keyed on
    the version, so an update that lands nowhere still exits 0 -- which is why apply must
    verify the recorded version afterwards instead of trusting the exit status."""
    env = _selection_env(tmp_path)
    installed_path = env["GET_HAIGGOH_INSTALLED_PLUGINS_FILE"]
    _write_json(installed_path, {"plugins": {"waypoints@haiggoh": [{"version": "0.5.1"}]}})
    mod = _load_cli(monkeypatch, env)
    monkeypatch.setattr(mod, "_remote_plugin_version", lambda url: ("0.6.0", None))
    monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **kw: _Ok())  # exits 0, changes nothing

    rc = mod.cmd_apply(only=["waypoints"])
    out = capsys.readouterr().out
    assert "NOT APPLIED" in out and "still 0.5.1" in out and "expected 0.6.0" in out
    assert rc == 1  # a no-op update is a failure, not an "ok"


def test_cli_apply_reports_ok_with_both_versions_when_the_update_lands(
        monkeypatch, capsys, tmp_path):
    env = _selection_env(tmp_path)
    installed_path = env["GET_HAIGGOH_INSTALLED_PLUGINS_FILE"]
    _write_json(installed_path, {"plugins": {"waypoints@haiggoh": [{"version": "0.5.1"}]}})
    mod = _load_cli(monkeypatch, env)
    monkeypatch.setattr(mod, "_remote_plugin_version", lambda url: ("0.6.0", None))

    def fake_run(cmd, **kwargs):
        _write_json(installed_path, {"plugins": {"waypoints@haiggoh": [{"version": "0.6.0"}]}})
        return _Ok()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    rc = mod.cmd_apply(only=["waypoints"])
    out = capsys.readouterr().out
    assert "update waypoints: ok (0.5.1 -> 0.6.0)" in out
    assert rc == 0


def test_cli_plan_shows_the_version_pair_for_an_outdated_plugin(monkeypatch, capsys, tmp_path):
    env = _selection_env(tmp_path)
    _write_json(env["GET_HAIGGOH_INSTALLED_PLUGINS_FILE"],
                {"plugins": {"waypoints@haiggoh": [{"version": "0.5.1"}]}})
    monkeypatch.delenv("GET_HAIGGOH_SKIP_REMOTE_SHA_CHECK", raising=False)
    env = {k: v for k, v in env.items() if k != "GET_HAIGGOH_SKIP_REMOTE_SHA_CHECK"}
    mod = _load_cli(monkeypatch, env)
    monkeypatch.setattr(mod, "_remote_plugin_version", lambda url: ("0.6.0", None))
    assert mod.cmd_plan(only=["waypoints"]) == 0
    assert "waypoints  (0.5.1 -> 0.6.0)" in capsys.readouterr().out


def test_cli_plan_diagnoses_an_unreadable_manifest_loudly(monkeypatch, capsys, tmp_path):
    """0.9.0: a manifest that cannot be verified must render the DIAGNOSIS loudly — the old
    silent fallback read a conflict-marker manifest as 'current' and hid free-agents 0.33.0
    for hours. The plan prints the fetched url, the problem, the meaning and the fix, and
    never says 'All current' while a plugin's published version is unverifiable."""
    env = _selection_env(tmp_path)
    installed_path = env["GET_HAIGGOH_INSTALLED_PLUGINS_FILE"]
    _write_json(installed_path, {"plugins": {"waypoints@haiggoh": [{"version": "0.5.1"}]}})
    mod = _load_cli(monkeypatch, env)
    monkeypatch.setattr(mod, "_remote_plugin_version", lambda url: (None, {
        "url": "https://example/HEAD/.claude-plugin/plugin.json",
        "problem": "manifest contains unresolved CONFLICT MARKERS",
        "meaning": "version-keyed installers read garbage and fall back",
        "fix": "resolve the manifest and move the tag"}))

    # 0.9.1: exit 1, not 0 — this assertion used to pin the bug (a blind plan exiting success)
    assert mod.cmd_plan(only=["waypoints"]) == 1
    out = capsys.readouterr().out
    assert "waypoints  0.5.1 (current)" not in out
    assert "CANNOT VERIFY THE PUBLISHED VERSION" in out
    assert "CONFLICT MARKERS" in out and "move the tag" in out
    assert "https://example/HEAD/.claude-plugin/plugin.json" in out
    assert "All haiggoh plugins are current." not in out
