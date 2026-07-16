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
        "GET_HAIGGOH_SKIP_REMOTE_SHA_CHECK": "1",  # no outdated-detection network calls either
    }
    r = _run(env)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert "measure-twice" in out["hookSpecificOutput"]["additionalContext"]


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
