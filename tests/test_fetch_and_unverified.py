"""0.9.1: the published-version check must not go blind on a TLS-intercepting network, and
when it cannot verify a plugin it must SAY so -- never render that plugin as '(current)'.

Measured 2026-10-26 on a corporate network whose proxy re-signs HTTPS: Python's urllib raised
CERTIFICATE_VERIFY_FAILED for every manifest while curl (macOS keychain) fetched the same URL
fine. plan printed the warning AND '= cost-tracker 0.20.1 (current)' and exited 0; apply printed
only '(current)'; the SessionStart hook cached the failed sweep for the whole day."""
import os
import ssl
import stat
import sys
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import get_haiggoh_core as c  # noqa: E402
from test_hook_and_cli import CLI, HOOK, _load_cli, _selection_env, _write_json  # noqa: E402

MANIFEST = b'{"name": "waypoints", "version": "0.6.0"}'
URL = "https://raw.githubusercontent.com/haiggoh/waypoints/HEAD/.claude-plugin/plugin.json"


def _tls_failure(*args, **kwargs):
    raise urllib.error.URLError(ssl.SSLCertVerificationError(
        1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
           "Missing Authority Key Identifier (_ssl.c:1144)"))


def _fake_curl(tmp_path, body=None, rc=0, stderr=""):
    """A curl stand-in that records its argv and prints `body` (or fails with `rc`)."""
    log = tmp_path / "curl-argv.log"
    out = tmp_path / "curl-body"
    out.write_bytes(body or b"")
    script = tmp_path / "fake curl"           # a SPACE in the path, on purpose
    script.write_text("#!/bin/sh\n"
                      f'printf "%s\\n" "$@" >> "{log}"\n'
                      f'[ {rc} -eq 0 ] && cat "{out}" && exit 0\n'
                      f'echo "{stderr}" >&2; exit {rc}\n')
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script, log


@pytest.fixture
def no_truststore(monkeypatch):
    monkeypatch.setenv("GET_HAIGGOH_NO_TRUSTSTORE", "1")


# --- fetch_url: one transport, two routes -------------------------------------------------

def test_fetch_falls_back_to_curl_when_urllib_fails_tls(monkeypatch, tmp_path, no_truststore):
    curl, log = _fake_curl(tmp_path, body=MANIFEST)
    monkeypatch.setenv("GET_HAIGGOH_CURL", str(curl))
    monkeypatch.setattr(urllib.request, "urlopen", _tls_failure)
    assert c.fetch_url(URL, timeout=3) == MANIFEST
    assert URL in log.read_text()


def test_fetch_does_not_call_curl_when_urllib_works(monkeypatch, tmp_path, no_truststore):
    curl, log = _fake_curl(tmp_path, body=b"WRONG")

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return MANIFEST

    monkeypatch.setenv("GET_HAIGGOH_CURL", str(curl))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp())
    assert c.fetch_url(URL, timeout=3) == MANIFEST
    assert not log.exists()


def test_fetch_raises_tls_kind_naming_both_attempts(monkeypatch, tmp_path, no_truststore):
    curl, _ = _fake_curl(tmp_path, rc=60, stderr="curl: (60) SSL certificate problem")
    monkeypatch.setenv("GET_HAIGGOH_CURL", str(curl))
    monkeypatch.setattr(urllib.request, "urlopen", _tls_failure)
    with pytest.raises(c.FetchError) as err:
        c.fetch_url(URL, timeout=3)
    assert err.value.kind == "tls"
    assert "CERTIFICATE_VERIFY_FAILED" in str(err.value) and "curl" in str(err.value)


def test_fetch_kind_is_network_for_a_plain_connection_failure(monkeypatch, tmp_path, no_truststore):
    curl, _ = _fake_curl(tmp_path, rc=6, stderr="curl: (6) Could not resolve host")
    monkeypatch.setenv("GET_HAIGGOH_CURL", str(curl))

    def refused(*a, **k):
        raise urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))

    monkeypatch.setattr(urllib.request, "urlopen", refused)
    with pytest.raises(c.FetchError) as err:
        c.fetch_url(URL, timeout=3)
    assert err.value.kind == "network"


def test_an_invalid_curl_override_fails_loudly_instead_of_using_the_default(
        monkeypatch, tmp_path, no_truststore):
    monkeypatch.setenv("GET_HAIGGOH_CURL", str(tmp_path / "no-such-curl"))
    monkeypatch.setattr(urllib.request, "urlopen", _tls_failure)
    with pytest.raises(c.FetchError) as err:
        c.fetch_url(URL, timeout=3)
    assert "GET_HAIGGOH_CURL" in str(err.value)


def test_tls_diagnostic_names_interception_not_just_connectivity():
    d = c.fetch_diagnostic(URL, c.FetchError("x", kind="tls"))
    assert "TLS" in d["problem"] or "TLS" in d["meaning"]
    assert "curl" in d["fix"]


# --- the CLI: unverifiable is a status of its own, and it is not success ------------------

def _unverifiable_cli(monkeypatch, tmp_path):
    env = _selection_env(tmp_path)
    del env["GET_HAIGGOH_SKIP_REMOTE_SHA_CHECK"]          # exercise the real fetch path
    env["GET_HAIGGOH_NO_TRUSTSTORE"] = "1"
    curl, _ = _fake_curl(tmp_path, rc=60, stderr="curl: (60) SSL certificate problem")
    env["GET_HAIGGOH_CURL"] = str(curl)
    _write_json(env["GET_HAIGGOH_INSTALLED_PLUGINS_FILE"],
                {"plugins": {"waypoints@haiggoh": [{"version": "0.5.1"}]}})
    monkeypatch.setattr(urllib.request, "urlopen", _tls_failure)
    return _load_cli(monkeypatch, env)


def test_plan_never_lists_an_unverifiable_plugin_as_current(monkeypatch, capsys, tmp_path):
    mod = _unverifiable_cli(monkeypatch, tmp_path)
    rc = mod.cmd_plan(only=["waypoints"])
    out = capsys.readouterr().out
    assert "CANNOT VERIFY" in out
    assert "waypoints  0.5.1 (current)" not in out
    assert "(unverified)" in out
    assert "all haiggoh plugins are current" not in out.lower()
    assert rc != 0


def test_apply_shows_the_diagnosis_and_fails_when_a_plugin_is_unverifiable(
        monkeypatch, capsys, tmp_path):
    mod = _unverifiable_cli(monkeypatch, tmp_path)
    monkeypatch.setenv("GET_HAIGGOH_NO_SHIMS", "1")
    rc = mod.cmd_apply(only=["waypoints"])
    out = capsys.readouterr().out
    assert "CANNOT VERIFY" in out
    assert "(current)" not in out
    assert "all haiggoh plugins are current" not in out.lower()
    assert rc == 1


def test_only_core_touches_the_network():
    """Choke point: the CLI and the hook must both reach the network through core.fetch_url,
    or the next transport fix lands on one route and the other stays blind."""
    for path in (CLI, HOOK):
        with open(path) as f:
            assert "urlopen" not in f.read(), path


# --- the hook: a failed sweep is not a finished day ---------------------------------------

def test_record_sweep_does_not_stamp_an_incomplete_day(tmp_path):
    stamp = str(tmp_path / "stamp.json")
    assert c.record_sweep(stamp, "2026-10-26", {"a": "1.0.0"}, unverified=["b"]) is False
    assert c.should_refresh(stamp, "2026-10-26") is True


def test_record_sweep_stamps_a_complete_day(tmp_path):
    stamp = str(tmp_path / "stamp.json")
    assert c.record_sweep(stamp, "2026-10-26", {"a": "1.0.0"}, unverified=[]) is True
    assert c.should_refresh(stamp, "2026-10-26") is False
    assert c.load_cached_versions(stamp) == {"a": "1.0.0"}


def test_nudge_names_plugins_it_could_not_verify():
    text = c.format_nudge([], [], unverified=["cost-tracker"])
    assert "cost-tracker" in text and "could not verify" in text.lower()
    assert c.format_nudge([], [], unverified=[]) == ""
