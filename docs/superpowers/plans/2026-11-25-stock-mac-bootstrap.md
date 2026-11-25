# Stock-Mac bootstrap (TUI Python + PATH) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, natively, then one final review of the whole branch. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On a colleague's stock Mac (no Homebrew, no admin, only `/usr/bin/python3` 3.9), installing
get-haiggoh from the marketplace yields a working Textual TUI and a `get-haiggoh` command in new terminals.

**Architecture:** (1) `bin/get-haiggoh-tui` builds its private venv on Python >= 3.10, preferring a local one
(Homebrew's included), else any `uv` on PATH, else a private checksum-pinned `uv` it downloads with the system
`curl` into the user's home; `uv` then fetches a standalone CPython (no admin). (2) New `get_haiggoh_pathrc.py`
adds a fenced PATH block for the shim dir to the user's login-shell startup file automatically when the dir is
not on PATH; the SessionStart hook and `apply`/`shims apply` call it; `shims path [--undo]` shows/removes it.

**Tech Stack:** Python stdlib only (must run on 3.9), system `curl`, uv 0.13.9 release binaries.

**Spec:** user decisions in session 2026-11-25: fix TUI fallback; "ship all the way"; PATH fix = *add
automatically*; "work with brew if installed but not be dependent on brew … without granting admin rights".

## Global Constraints

- Launcher code runs under `/usr/bin/python3` 3.9.6: no 3.10+ syntax (no `match`, no `X | Y` types).
- Python floor for the venv: `MIN_PY = (3, 10)`.
- Pinned uv: `UV_VERSION = "0.13.9"`; sha256 `aarch64-apple-darwin` = `5aeca67f2283f75235de40d0bd9c0a5bbc5fce23b6d48b3bf9fa1b2db08382ca`, `x86_64-apple-darwin` = `617a3211261b0fc739562f0071aa34e9739797c510208ede8e2977c30903d041` (verified against release `.sha256` files AND GitHub API digests).
- Every uv call gets env `UV_SYSTEM_CERTS=1` and `UV_NATIVE_TLS=1` (corp MITM; new + old flag names).
- Nothing requires admin or Homebrew; no user-visible message may offer `brew` as the only route.
- Never write the user's real rc file in tests: conftest sets `GET_HAIGGOH_NO_PATH_EDIT=1` autouse.
- New env vars, each in `--help`: `GET_HAIGGOH_NO_PATH_EDIT=1`, `GET_HAIGGOH_TOOLS_DIR` (default `~/.local/share/get-haiggoh/tools`), `GET_HAIGGOH_NO_UV_DOWNLOAD=1`.
- Version 0.12.0 (new behaviour), bumped in `.claude-plugin/plugin.json`; portable regen; CHANGELOG.

## Review Focus

1. bash user with only `~/.profile` — creating `~/.bash_profile` would stop `.profile` loading → append to the first EXISTING of `.bash_profile`, `.bash_login`, `.profile`.
2. rc file is a symlink (dotfiles repo) → append through it, never replace it.
3. Hook runs every session → block must be written once (idempotent: block present ⇒ no write, no note).
4. Interactive-login probe of a slow/noisy rc → bounded timeout, markers around `$PATH`, failure ⇒ treat as "unknown", still append (block is self-guarding: only prepends when absent).
5. Download corrupted / swapped → sha mismatch ⇒ nothing installed, RuntimeError naming the mismatch.

---

### Task 1: Admin-free Python route in the TUI bootstrap

**Files:** Modify `bin/get-haiggoh-tui`; Test `tests/test_tui_bootstrap.py`

**Interfaces — Produces:**
- `uv_asset() -> str | None` (`uv-<arch>-apple-darwin.tar.gz` from `platform.machine()`; None off macOS)
- `fetch_uv(dest_dir: str, url: str, sha256: str) -> str` — curl to temp, verify sha, extract ONLY member `*/uv` by name (no `extractall`), chmod 0755, atomic rename into `dest_dir/uv`; returns path; RuntimeError on any failure, nothing left in `dest_dir`.
- `private_uv() -> str | None` — cached `<tools>/uv-0.13.9/uv` or `fetch_uv(...)`; None when `GET_HAIGGOH_NO_UV_DOWNLOAD` set or no asset.
- `uv_env() -> dict` — `os.environ` + the two cert vars.
- `create_venv` order: base python → `uv` on PATH → `private_uv()`; uv form `uv venv --clear --python <base or ">=3.10"> <venv>`.
- `NEED_PY` text: names no-admin fix (`get-haiggoh` downloads a private uv; or install any Python >= 3.10) — no brew-only advice.

- [ ] Step 1: tests — `test_fetch_uv_installs_verified_binary` (build tar with `uv-x/uv`, file:// URL, correct sha ⇒ executable at returned path); `test_fetch_uv_rejects_checksum_mismatch` (wrong sha ⇒ RuntimeError containing "sha256", `dest_dir` has no `uv`); `test_create_venv_uses_private_uv_when_nothing_else` (find_base_python→None, PATH without uv, private_uv stubbed to fake uv logging args ⇒ first call `venv --clear --python >=3.10`); `test_no_download_env_names_the_fix` (GET_HAIGGOH_NO_UV_DOWNLOAD=1 ⇒ RuntimeError with "3.10", without "brew install python" as sole route). Update `test_no_floor_python_and_no_uv_names_the_fix` to stub `private_uv` → None.
- [ ] Step 2: run `python3 -m pytest tests/test_tui_bootstrap.py -q` → new tests FAIL.
- [ ] Step 3: implement; uv calls pass `env=uv_env()` (extend `_run(cmd, env=None)`).
- [ ] Step 4: same run → all PASS; `/usr/bin/python3 -c "import ast;ast.parse(open('bin/get-haiggoh-tui').read())"` OK.
- [ ] Step 5: commit `feat(tui): admin-free Python route via a pinned private uv`.

### Task 2: `get_haiggoh_pathrc.py` — the PATH block

**Files:** Create `get_haiggoh_pathrc.py`; Test `tests/test_pathrc.py`; Modify `tests/conftest.py` (autouse `GET_HAIGGOH_NO_PATH_EDIT=1`)

**Interfaces — Produces:**
- `BEGIN = "# >>> get-haiggoh PATH (added automatically; undo: get-haiggoh shims path --undo) >>>"`, `END = "# <<< get-haiggoh PATH <<<"`
- `rc_file(shell: str, home: str, zdotdir: str | None) -> str | None` — zsh ⇒ `<zdotdir or home>/.zprofile`; bash ⇒ first existing of `.bash_profile`, `.bash_login`, `.profile`, else `.bash_profile`; other ⇒ None.
- `render_block(directory: str, home: str) -> str` — `$HOME/…` form when under home; body `case ":$PATH:" in *":DIR:"*) ;; *) export PATH="DIR:$PATH" ;; esac`.
- `has_block(path) -> bool`; `remove_block(path) -> bool` (rewrites the realpath in place, keeps mode).
- `login_path(shell: str, timeout: float = 5) -> list | None` — `[shell, "-lic", 'printf "__GH__%s__GH__" "$PATH"']`, parse between markers.
- `ensure_on_path(directory: str) -> str` — '' when opted out / on `os.environ` PATH / block present / on login PATH; else backup rc (shim-backup dir) and APPEND block (open `"a"`, follows symlinks); returns `"👨🏻‍💻 get-haiggoh: added <dir> to your PATH in <rc> — open a new terminal (undo: get-haiggoh shims path --undo)"`; unsupported shell ⇒ warning line with the manual export; never raises.

- [ ] Step 1: tests, each with tmp HOME/ZDOTDIR and env flag cleared: zsh appends once (second call '' and one BEGIN); bash with only `.profile` appends to `.profile` and creates no `.bash_profile`; symlinked rc stays a symlink and target gains block; `remove_block` restores original bytes; on-PATH dir ⇒ '' and file untouched; fish ⇒ warning, no file; opt-out env ⇒ ''.
- [ ] Step 2: run `python3 -m pytest tests/test_pathrc.py -q` → FAIL (module missing).
- [ ] Step 3: implement.
- [ ] Step 4: run → PASS; plus full `pytest -q -n auto tests` still green (autouse flag).
- [ ] Step 5: commit `feat(shims): add the shim dir to the login shell PATH automatically`.

### Task 3: Wire into hook and CLI

**Files:** Modify `hooks/check-installed.py` (`_add_missing_shims`), `bin/get-haiggoh.py` (`cmd_shims`, dispatch, `--help`), `get_haiggoh_shims.py` (`format_report` warning text); Test `tests/test_hook_shims.py`, `tests/test_shims_cli.py`

**Interfaces — Consumes:** `ensure_on_path(directory) -> str`, `has_block`, `remove_block`, `rc_file` from Task 2.

- [ ] Step 1: tests — hook with flag cleared + tmp ZDOTDIR + shim dir not on PATH ⇒ banner contains "added" and `.zprofile` has BEGIN; second hook run ⇒ no PATH note; `shims path` prints status (rc file, on PATH yes/no) and writes nothing; `shims path --undo` removes block; `--help` lists `shims path` and the three env vars.
- [ ] Step 2: run both test files → FAIL.
- [ ] Step 3: hook appends `ensure_on_path(s.shim_dir())` note when any haiggoh shim exists in the dir; `cmd_shims("apply")` and `apply` print it; add `path` mode (+ `--undo`) to argv parsing (unknown flag ⇒ exit 2).
- [ ] Step 4: run → PASS.
- [ ] Step 5: commit `feat(cli): shims path [--undo]; hook + apply ensure the shim dir is on PATH`.

### Task 4: Release prep + delivery-level dogfood

- [ ] Step 1: version 0.12.0 in `.claude-plugin/plugin.json`; replace the uncommitted 0.11.2 CHANGELOG entry with a 0.12.0 entry covering both fixes; README install section mentions no brew/admin needed; `python3 scripts/build-portable.py`.
- [ ] Step 2: stock-Mac dogfood under `env -i HOME=<tmp> PATH=/usr/bin:/bin`, driven by `/usr/bin/python3`, with `GET_HAIGGOH_TUI_VENV=<tmp>/venv`, `GET_HAIGGOH_TOOLS_DIR=<tmp>/tools`, `UV_PYTHON_INSTALL_DIR=<tmp>/py`, `UV_CACHE_DIR=<tmp>/uvcache`. Homebrew's python3 is a hardcoded candidate on this machine, so the driver loads the bootstrap module and sets `find_base_python = lambda c=None: None` before `ensure_venv` — this exercises the REAL pinned-uv download and a REAL uv-managed CPython. Pass ⇒ `<tmp>/tools/uv-0.13.9/uv` exists, venv `pyvenv.cfg` home under `<tmp>/py`, `get-haiggoh-tui --check` ⇒ `status: ok`. Then the hook in `env -i HOME=<tmp> SHELL=/bin/zsh ZDOTDIR=<tmp> PATH=/usr/bin:/bin` (flag cleared) ⇒ `<tmp>/.zprofile` has the block and `ZDOTDIR=<tmp> HOME=<tmp> /bin/zsh -lc 'command -v get-haiggoh'` prints the shim path.
- [ ] Step 3: full gate (rtc-ship.json `test_cmd`), `build-portable.py --check` clean.
- [ ] Step 4: commit `chore(0.12.0): version, changelog, portable regen`.

### Task 5: Ship (authorized: through release + refresh)

- [ ] `rtc-ship` from this worktree: gate → merge → tag `v0.12.0` → release → refresh → verify `get-haiggoh plan` sees 0.12.0 → dogfood installed copy (`get-haiggoh-tui --check`, `get-haiggoh shims path`).
