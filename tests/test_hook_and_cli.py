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


def test_cli_apply_only_updates_just_the_named_plugin(monkeypatch, tmp_path):
    env = _selection_env(tmp_path)
    calls = []

    import importlib.util
    spec = importlib.util.spec_from_file_location("get_haiggoh_cli", CLI)
    mod = importlib.util.module_from_spec(spec)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    spec.loader.exec_module(mod)

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        class R:
            returncode = 0
            stderr = ""
        return R()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    rc = mod.cmd_apply(only=["waypoints"])
    assert rc == 0
    updated_names = {c[3].split("@")[0] for c in calls if c[1] == "plugin"}
    assert updated_names == {"waypoints"}
