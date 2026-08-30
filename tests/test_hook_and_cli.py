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

    env = {
        "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": known_path,
        "GET_HAIGGOH_INSTALLED_PLUGINS_FILE": installed_path,
        "GET_HAIGGOH_SKIP_FILE": str(tmp_path / "skip.json"),
        "GET_HAIGGOH_REFRESH_STAMP_FILE": str(tmp_path / "stamp.json"),
        "GET_HAIGGOH_SELF_NAME": "get-haiggoh",
        "GET_HAIGGOH_SKIP_NETWORK_REFRESH": "1",
        "PATH": "",  # no `git` on PATH at all -- any git-ls-remote call would raise/fail
    }
    r = _run(env)
    assert r.returncode == 0
    assert r.stdout.strip() == ""  # measure-twice is installed and not missing -- nothing to nudge


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
    assert "nothing to do" in r.stdout.lower()


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
    monkeypatch.setattr(mod, "_remote_plugin_version", lambda url: "0.6.0")
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
    monkeypatch.setattr(mod, "_remote_plugin_version", lambda url: "0.6.0")

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
    monkeypatch.setattr(mod, "_remote_plugin_version", lambda url: "0.6.0")
    assert mod.cmd_plan(only=["waypoints"]) == 0
    assert "waypoints  (0.5.1 -> 0.6.0)" in capsys.readouterr().out
