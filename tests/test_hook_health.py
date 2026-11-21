"""Repair only verified missing manual hook duplicates; preserve every other entry."""
import json
from pathlib import Path
import pytest
import get_haiggoh_hook_health as health


def setup(tmp_path):
    dead = tmp_path / ".claude/scripts/local-queue-stop-hook.py"
    live = tmp_path / ".codex/plugins/cache/haiggoh/free-agents/0.59.4/bin/local-queue-stop-hook.py"
    live.parent.mkdir(parents=True)
    live.write_text("# maintained hook\n")
    command = f'python3 "{dead}"'
    config = tmp_path / "hooks.json"
    config.write_text(json.dumps({"note": "keep", "hooks": {"Stop": [{"hooks": [
        {"type": "command", "command": command},
        {"type": "command", "command": "echo valid"}]}]}}))
    config.chmod(0o600)
    metadata = [{"eventName": "stop", "matcher": None, "command": f'python3 "{live}"',
                 "source": "plugin", "pluginId": "free-agents@haiggoh", "enabled": True,
                 "trustStatus": "trusted", "sourcePath": str(live.parent.parent / "hooks/hooks.json")}]
    return config, metadata


def test_repair_preserves_unrelated_entries_and_exact_backup(tmp_path):
    config, metadata = setup(tmp_path)
    before = config.read_bytes()
    result = health.repair_manual_hooks(config, metadata, apply=True)
    assert len(result["repaired"]) == 1
    assert Path(result["backup"]).read_bytes() == before
    assert config.stat().st_mode & 0o777 == 0o600
    assert json.loads(config.read_text()) == {"note": "keep", "hooks": {"Stop": [{"hooks": [
        {"type": "command", "command": "echo valid"}]}]}}
    assert health.repair_manual_hooks(config, metadata, apply=True)["repaired"] == []


def test_check_only_never_writes(tmp_path):
    config, metadata = setup(tmp_path)
    before = config.read_bytes()
    result = health.repair_manual_hooks(config, metadata)
    assert len(result["repairable"]) == 1
    assert config.read_bytes() == before
    assert result["backup"] is None


@pytest.mark.parametrize("changes", [
    {"trustStatus": "untrusted"}, {"enabled": False}, {"matcher": "Bash"},
    {"pluginId": "unrelated@haiggoh"}, {"eventName": "preToolUse"},
])
def test_unverified_successor_is_not_used(tmp_path, changes):
    config, metadata = setup(tmp_path)
    metadata[0].update(changes)
    before = config.read_bytes()
    result = health.repair_manual_hooks(config, metadata, apply=True)
    assert result["repaired"] == []
    assert result["unresolved"]
    assert config.read_bytes() == before


def test_custom_flags_are_not_discarded(tmp_path):
    config, metadata = setup(tmp_path)
    doc = json.loads(config.read_text())
    doc["hooks"]["Stop"][0]["hooks"][0]["command"] += " --custom"
    config.write_text(json.dumps(doc))
    assert health.repair_manual_hooks(config, metadata, apply=True)["unresolved"]
    assert "--custom" in config.read_text()


def test_ambiguous_successors_do_not_repair(tmp_path):
    config, metadata = setup(tmp_path)
    metadata.append(dict(metadata[0], command=metadata[0]["command"] + " --custom"))
    # A second exact candidate at another root is genuinely ambiguous.
    other = tmp_path / "other/bin/local-queue-stop-hook.py"
    other.parent.mkdir(parents=True)
    other.write_text("# another copy\n")
    metadata.append(dict(metadata[0], command=f'python3 "{other}"',
                         sourcePath=str(tmp_path / "other/hooks/hooks.json")))
    assert health.repair_manual_hooks(config, metadata, apply=True)["unresolved"]


def test_corrupt_config_is_never_rewritten(tmp_path):
    config, metadata = setup(tmp_path)
    config.write_text("{")
    assert health.repair_manual_hooks(config, metadata, apply=True)["unresolved"]
    assert config.read_text() == "{"


def test_concurrent_change_is_preserved(tmp_path, monkeypatch):
    config, metadata = setup(tmp_path)
    real = health.atomic_write
    def race(path, expected, replacement):
        path.write_text('{"hooks": {}, "user": "new work"}')
        return real(path, expected, replacement)
    monkeypatch.setattr(health, "atomic_write", race)
    result = health.repair_manual_hooks(config, metadata, apply=True)
    assert result["repaired"] == []
    assert result["unresolved"]
    assert json.loads(config.read_text())["user"] == "new work"


def test_codex_startup_skips_claude_refresh_and_shims(tmp_path, monkeypatch, capsys):
    import importlib.util
    import io
    import sys
    spec = importlib.util.spec_from_file_location("hook_health_startup", Path(__file__).parents[1] / "hooks/check-installed.py")
    hook = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(hook)
    except SystemExit:
        pass
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    payload = {"cwd": str(tmp_path), "transcript_path": str(tmp_path / "sessions/rollout.jsonl")}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(health, "codex_notice", lambda p: "verified recovery notice")
    def forbidden(*a):
        raise AssertionError("Codex must not touch the Claude registry or shims")
    monkeypatch.setattr(hook, "_add_missing_shims", forbidden)
    monkeypatch.setattr(hook, "_nudge_banner", forbidden)
    capsys.readouterr()
    hook.main()
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"] == "verified recovery notice"


@pytest.mark.parametrize("suffix", [" --flag;echo changed", " >output", " --value=$USER", " --value=\x60whoami\x60"])
def test_shell_expansion_or_compound_command_is_never_repaired(tmp_path, suffix):
    config, metadata = setup(tmp_path)
    doc = json.loads(config.read_text())
    doc["hooks"]["Stop"][0]["hooks"][0]["command"] += suffix
    metadata[0]["command"] += suffix
    config.write_text(json.dumps(doc))
    before = config.read_bytes()
    result = health.repair_manual_hooks(config, metadata, apply=True)
    assert result["repaired"] == []
    assert result["unresolved"]
    assert config.read_bytes() == before


def test_claude_payload_ignores_invalid_codex_override(monkeypatch):
    monkeypatch.setenv("CODEX_HOME", "not-an-absolute-path")
    assert health.is_codex_payload({"transcript_path": str(Path.home() / ".claude/projects/session.jsonl")}) is False


def test_custom_claude_payload_ignores_invalid_codex_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("CODEX_HOME", "not-an-absolute-path")
    assert health.is_codex_payload({"transcript_path": str(tmp_path / "projects/session.jsonl")}) is False


def test_ambiguous_json_keys_are_never_rewritten(tmp_path):
    config, metadata = setup(tmp_path)
    doc = config.read_text()
    config.write_text(doc.replace('"note": "keep"', '"note": "keep", "note": "user work"'))
    before = config.read_bytes()
    result = health.repair_manual_hooks(config, metadata, apply=True)
    assert result["repaired"] == []
    assert result["unresolved"]
    assert config.read_bytes() == before


def test_symlink_is_not_replaced(tmp_path):
    config, metadata = setup(tmp_path)
    link = tmp_path / "linked-hooks.json"
    link.symlink_to(config)
    before = config.read_bytes()
    result = health.repair_manual_hooks(link, metadata, apply=True)
    assert result["repaired"] == []
    assert result["unresolved"]
    assert link.is_symlink()
    assert config.read_bytes() == before


def test_healthy_codex_startup_does_not_query_native_inventory(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "hooks.json").write_text('{"hooks": {}}')
    def forbidden(*args):
        raise AssertionError("healthy startup must not query RPC")
    monkeypatch.setattr(health, "native_hooks", forbidden)
    assert health.codex_notice({"cwd": str(tmp_path)}) == ""


def test_codex_repair_notice_describes_owning_server_reload(tmp_path, monkeypatch):
    config, metadata = setup(tmp_path)
    config.rename(tmp_path / "hooks.json")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    monkeypatch.setattr(health, "native_hooks", lambda cwd: metadata)
    notice = health.codex_notice({"cwd": str(tmp_path)})
    assert "0.171.0" in notice and "owning" in notice
    assert "config/batchWrite" in notice and "reloadUserConfig" in notice
    assert "new chat" in notice


@pytest.mark.parametrize("respond", [True, False])
def test_native_inventory_is_bounded_and_cleans_up_its_own_child(tmp_path, monkeypatch, respond):
    import subprocess
    import sys
    import time
    real_popen = subprocess.Popen
    launched = []
    program = ('import json, sys; '
               'print(json.dumps({"id": 1, "result": {}}), flush=True); '
               + ('print(json.dumps({"id": 2, "result": {"data": [{"hooks": [{"key": "test"}]}]}}), flush=True); '
                  if respond else '') + 'sys.stdin.read()')
    def launch(command, **kwargs):
        assert command == ["codex", "app-server", "--stdio"]
        child = real_popen([sys.executable, "-c", program], **kwargs)
        launched.append(child)
        return child
    monkeypatch.setattr(health.subprocess, "Popen", launch)
    started = time.monotonic()
    if respond:
        assert health.native_hooks(tmp_path) == [{"key": "test"}]
    else:
        with pytest.raises(ValueError, match="eight-second deadline"):
            health.native_hooks(tmp_path)
    assert time.monotonic() - started < 11
    assert len(launched) == 1
    assert launched[0].poll() is not None
