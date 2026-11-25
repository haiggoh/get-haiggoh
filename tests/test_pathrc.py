"""The PATH block get-haiggoh adds to the login shell's startup file (stock Macs do not
have ~/.local/bin on PATH). Every test points HOME/ZDOTDIR at a tmp dir and clears the
conftest opt-out itself, so the real ~/.zprofile is never touched.

Usage: python3 -m pytest tests/test_pathrc.py -q
"""
import os
import subprocess

import pytest

import get_haiggoh_pathrc as p


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "my home"
    (h / ".local" / "bin").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("ZDOTDIR", str(h))
    monkeypatch.setenv("SHELL", "/bin/zsh")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("GET_HAIGGOH_SHIM_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.delenv("GET_HAIGGOH_NO_PATH_EDIT", raising=False)
    return h


def shim_dir(home):
    return str(home / ".local" / "bin")


def test_zsh_appends_block_once(home):
    note = p.ensure_on_path(shim_dir(home))
    assert "added" in note and ".zprofile" in note and "--undo" in note
    text = (home / ".zprofile").read_text()
    assert text.count(p.BEGIN) == 1 and p.END in text
    assert "$HOME/.local/bin" in text
    assert p.ensure_on_path(shim_dir(home)) == ""
    assert (home / ".zprofile").read_text().count(p.BEGIN) == 1


def test_block_really_puts_dir_on_path_once(home):
    p.ensure_on_path(shim_dir(home))
    rc = home / ".zprofile"
    out = subprocess.run(["/bin/zsh", "-fc", f'source "{rc}"; source "{rc}"; print -r -- "$PATH"'],
                         capture_output=True, text=True, env={"HOME": str(home), "PATH": "/usr/bin:/bin"})
    assert out.stdout.strip().split(":").count(shim_dir(home)) == 1


def test_bash_with_only_profile_appends_to_profile(home, monkeypatch):
    monkeypatch.setenv("SHELL", "/bin/bash")
    (home / ".profile").write_text("existing\n")
    note = p.ensure_on_path(shim_dir(home))
    assert ".profile" in note
    text = (home / ".profile").read_text()
    assert text.startswith("existing\n") and p.BEGIN in text
    assert not (home / ".bash_profile").exists(), "creating it would stop .profile loading"


def test_symlinked_rc_stays_a_symlink(home, tmp_path):
    real = tmp_path / "dotfiles" / "zprofile"
    real.parent.mkdir()
    real.write_text("x\n")
    (home / ".zprofile").symlink_to(real)
    p.ensure_on_path(shim_dir(home))
    assert (home / ".zprofile").is_symlink()
    assert p.BEGIN in real.read_text()


def test_remove_block_restores_original_bytes(home):
    rc = home / ".zprofile"
    rc.write_text("orig\n")
    p.ensure_on_path(shim_dir(home))
    assert p.remove_block(str(rc)) is True
    assert rc.read_text() == "orig\n"
    assert p.remove_block(str(rc)) is False


def test_has_block_requires_begin_and_end(home):
    rc = home / ".zprofile"
    rc.write_text("x\n" + p.BEGIN + "\ncase ...")  # truncated: BEGIN without END
    assert p.has_block(str(rc)) is False
    rc.write_text("x\n" + p.render_block(shim_dir(home), str(home)))
    assert p.has_block(str(rc)) is True


def test_truncated_append_is_repaired_on_next_run(home):
    """A previous append cut short (BEGIN, no END) left an unclosed `case` in the rc and made
    has_block() lie — the next run must remove the wreckage and add one whole, parseable
    block (review 2026-11-25, finding 4)."""
    rc = home / ".zprofile"
    rc.write_text("orig\n" + p.BEGIN + '\ncase ":$PATH:" in\n')  # killed mid-write
    note = p.ensure_on_path(shim_dir(home))
    text = rc.read_text()
    assert text.startswith("orig\n"), text
    assert text.count(p.BEGIN) == 1 and p.END in text, text
    assert "added" in note, note
    r = subprocess.run(["/bin/zsh", "-n", str(rc)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr  # the rc must still parse as zsh


def test_remove_block_cleans_a_truncated_block(home):
    rc = home / ".zprofile"
    rc.write_text("orig\n" + p.BEGIN + '\ncase ":$PATH:" in\n')
    assert p.remove_block(str(rc)) is True
    assert rc.read_text() == "orig\n"


def test_backup_taken_before_editing(home, tmp_path):
    (home / ".zprofile").write_text("orig\n")
    p.ensure_on_path(shim_dir(home))
    backups = list((tmp_path / "backups").iterdir())
    assert len(backups) == 1 and backups[0].read_text() == "orig\n"


def test_dir_already_on_path_writes_nothing(home, monkeypatch):
    monkeypatch.setenv("PATH", shim_dir(home) + ":/usr/bin:/bin")
    assert p.ensure_on_path(shim_dir(home)) == ""
    assert not (home / ".zprofile").exists()


def test_dir_on_login_shell_path_writes_nothing(home):
    # the user's own startup file already adds it (this session's PATH just predates it)
    (home / ".zprofile").write_text(f'export PATH="{shim_dir(home)}:$PATH"\n')
    assert p.ensure_on_path(shim_dir(home)) == ""
    assert p.BEGIN not in (home / ".zprofile").read_text()


def test_unsupported_shell_warns_without_writing(home, monkeypatch):
    monkeypatch.setenv("SHELL", "/opt/fish/bin/fish")
    note = p.ensure_on_path(shim_dir(home))
    assert "not on your PATH" in note and "export PATH" in note
    assert sorted(os.listdir(home)) == [".local"]


def test_opt_out_env_writes_nothing(home, monkeypatch):
    monkeypatch.setenv("GET_HAIGGOH_NO_PATH_EDIT", "1")
    assert p.ensure_on_path(shim_dir(home)) == ""
    assert not (home / ".zprofile").exists()
