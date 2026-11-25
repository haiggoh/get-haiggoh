"""Put the shim directory on the user's login-shell PATH.

A stock Mac does not have ~/.local/bin on PATH, so the `get-haiggoh` shortcut (and every
other haiggoh shim) did not resolve in a new terminal. ensure_on_path() appends ONE fenced,
labelled block to the login shell's startup file — automatically, by the user's decision
(2026-11-25) — reports it, and `get-haiggoh shims path --undo` removes it again.

Choices that are not obvious:
- zsh: $ZDOTDIR/.zprofile (or ~/.zprofile): read by every login shell, which is what macOS
  terminals start. bash: the FIRST EXISTING of .bash_profile/.bash_login/.profile, because
  bash reads only the first one present — creating .bash_profile would silence a .profile.
  Any other shell: no edit, a warning with the line to add.
- APPEND (open "a"), never temp+rename: a dotfiles-managed rc is often a symlink, and a
  rename would replace the link with a plain file.
- The block guards itself (`case ":$PATH:"`), so a wrong guess about the current PATH can
  only ever produce a no-op, never a duplicate entry.
- Runs under the system python3 (3.9 on macOS): no 3.10+ syntax. Never raises.

Env: GET_HAIGGOH_NO_PATH_EDIT=1 never edits startup files; GET_HAIGGOH_SHIM_BACKUP_DIR
receives a copy of the startup file before the edit.
"""
import os
import shutil
import subprocess
import time

BEGIN = "# >>> get-haiggoh PATH (added automatically; undo: get-haiggoh shims path --undo) >>>"
END = "# <<< get-haiggoh PATH <<<"
_MARK = "__GH_PATH__"
_UNSAFE = ('"', "$", "`", "\\")
_TAG = "👨🏻‍💻 get-haiggoh:"


def _shell_name(shell):
    return os.path.basename(shell or "")


def rc_file(shell, home, zdotdir=None):
    """The startup file a login shell of this kind reads, or None for shells we do not edit."""
    name = _shell_name(shell)
    if name == "zsh":
        return os.path.join(zdotdir or home, ".zprofile")
    if name == "bash":
        for candidate in (".bash_profile", ".bash_login", ".profile"):
            path = os.path.join(home, candidate)
            if os.path.lexists(path):
                return path
        return os.path.join(home, ".bash_profile")
    return None


def _shell_path(directory, home):
    """`$HOME/...` when the directory is under home (portable across renamed homes)."""
    home = home.rstrip(os.sep)
    if directory == home or directory.startswith(home + os.sep):
        return "$HOME" + directory[len(home):]
    return directory


def render_block(directory, home):
    d = _shell_path(directory, home)
    return (f'{BEGIN}\ncase ":$PATH:" in\n  *":{d}:"*) ;;\n  *) export PATH="{d}:$PATH" ;;\n'
            f"esac\n{END}\n")


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def has_block(path):
    """True only for a COMPLETE block (BEGIN and END) — a truncated append is not a block."""
    text = _read(path)
    return BEGIN in text and END in text


def _truncated(path):
    """BEGIN present but END missing: a previous append was cut short mid-block."""
    text = _read(os.path.realpath(path))
    return BEGIN in text and END not in text


def _drop_truncated(path):
    """Remove a truncated block (from BEGIN to EOF — the block is always appended last).
    True if it removed something."""
    real = os.path.realpath(path)
    text = _read(real)
    start = text.find(BEGIN)
    if start < 0 or END in text:
        return False
    with open(real, "w", encoding="utf-8") as f:
        f.write(text[:start])
    return True


def remove_block(path):
    """Remove the block in place (through a symlink, keeping the file's mode). True if removed."""
    real = os.path.realpath(path)
    text = _read(real)
    start = text.find(BEGIN)
    if start < 0:
        return False
    end = text.find(END, start)
    if end < 0:
        # truncated block: remove from BEGIN to EOF so --undo still works
        with open(real, "w", encoding="utf-8") as f:
            f.write(text[:start])
        return True
    end += len(END)
    if text[end:end + 1] == "\n":
        end += 1
    with open(real, "w", encoding="utf-8") as f:
        f.write(text[:start] + text[end:])
    return True


def login_path(shell, timeout=5):
    """PATH as a fresh interactive login shell sees it, or None when it cannot be learned."""
    try:
        r = subprocess.run([shell, "-lic", f'printf "{_MARK}%s{_MARK}" "$PATH"'],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    parts = r.stdout.split(_MARK)
    return parts[1].split(os.pathsep) if len(parts) >= 3 else None


def _contains(entries, directory):
    want = os.path.realpath(os.path.expanduser(directory))
    return any(e and os.path.realpath(os.path.expanduser(e)) == want for e in entries)


def _tilde(path, home):
    return "~" + path[len(home):] if path.startswith(home + os.sep) else path


def _backup(path):
    import get_haiggoh_shims as s
    os.makedirs(s.backup_dir(), exist_ok=True)
    dest = os.path.join(s.backup_dir(),
                        f"{os.path.basename(path)}.{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(os.path.realpath(path), dest)


def ensure_on_path(directory):
    """Make `directory` resolve in new terminals. Returns a one-line note for the user when
    it changed something or needs the user ('' otherwise). Never raises."""
    manual = f'export PATH="{directory}:$PATH"'
    try:
        if os.environ.get("GET_HAIGGOH_NO_PATH_EDIT"):
            return ""
        if _contains(os.environ.get("PATH", "").split(os.pathsep), directory):
            return ""
        home = os.path.expanduser("~")
        shell = os.environ.get("SHELL") or ""
        rc = rc_file(shell, home, os.environ.get("ZDOTDIR"))
        if rc is None:
            return (f"{_TAG} warning: {directory} is not on your PATH and get-haiggoh does not "
                    f"edit {_shell_name(shell) or 'this shell'}'s startup files — add: {manual}")
        if _truncated(rc):
            # a previous append was cut short (BEGIN without END, e.g. killed mid-write):
            # back up and remove the wreckage — an unclosed `case` breaks the rc for every
            # login — then fall through and append one whole block (review 2026-11-25)
            if os.path.lexists(rc):
                _backup(rc)
            _drop_truncated(rc)
        if has_block(rc):
            return ""  # already added; a new terminal picks it up
        lp = login_path(shell)
        if lp is not None and _contains(lp, directory):
            return ""
        if any(ch in directory for ch in _UNSAFE):
            return f"{_TAG} warning: {directory} is not on your PATH — add: {manual}"
        existing = _read(rc)
        if os.path.lexists(rc):
            _backup(rc)
        with open(rc, "a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(render_block(directory, home))
        return (f"{_TAG} added {_tilde(directory, home)} to your PATH in {_tilde(rc, home)} — "
                f"open a new terminal for it to take effect (undo: get-haiggoh shims path --undo)")
    except Exception as exc:  # a startup hook must never fail the session
        return f"{_TAG} warning: could not put {directory} on your PATH ({exc}) — add: {manual}"
