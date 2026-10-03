import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import get_haiggoh_core as c  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_shim_dirs(tmp_path_factory, monkeypatch):
    """No test may ever touch the real ~/.local/bin or the real backup dir, even by accident."""
    base = tmp_path_factory.mktemp("shim-isolation")
    monkeypatch.setenv("GET_HAIGGOH_SHIM_DIR", str(base / "bin"))
    monkeypatch.setenv("GET_HAIGGOH_SHIM_BACKUP_DIR", str(base / "backups"))


class World:
    """A fake machine under tmp_path. The directory name contains a SPACE on purpose."""

    def __init__(self, tmp_path, monkeypatch):
        self.home = tmp_path / "my home"
        self.bin = self.home / "bin"
        self.backups = self.home / "backups"
        self.cache = self.home / "cache" / "haiggoh"
        self.record = self.home / "installed_plugins.json"
        self.bin.mkdir(parents=True)
        self.paths = {}
        for key, value in self.env_overrides().items():
            monkeypatch.setenv(key, value)

    def env_overrides(self):
        return {
            "GET_HAIGGOH_SHIM_DIR": str(self.bin),
            "GET_HAIGGOH_SHIM_BACKUP_DIR": str(self.backups),
            "GET_HAIGGOH_INSTALLED_PLUGINS_FILE": str(self.record),
            "GET_HAIGGOH_CACHE_DIR": str(self.cache),
            "GET_HAIGGOH_KNOWN_MARKETPLACES_FILE": str(self.home / "no-marketplaces.json"),
            "GET_HAIGGOH_SKIP_FILE": str(self.home / "skip.json"),
            "GET_HAIGGOH_REFRESH_STAMP_FILE": str(self.home / "stamp.json"),
            "GET_HAIGGOH_SKIP_REMOTE_VERSION_CHECK": "1",
            "GET_HAIGGOH_SKIP_NETWORK_REFRESH": "1",
        }

    def plugin(self, name, version, commands, declare=True, executable=True):
        root = self.cache / name / version
        (root / "bin").mkdir(parents=True)
        for cmd in commands:
            script = root / "bin" / cmd
            script.write_text(f'#!/usr/bin/env bash\necho "{name}-{version}:{cmd}:$*"\n')
            script.chmod(0o755 if executable else 0o644)
        if declare:
            (root / "shortcuts").write_text("# shortcuts\n" + "\n".join(commands) + "\n")
        self.paths[name] = str(root)
        self.write_record()
        return root

    def write_record(self):
        plugins = {f"{n}@haiggoh": [{"version": os.path.basename(p), "installPath": p}]
                   for n, p in self.paths.items()}
        self.record.write_text(json.dumps({"plugins": plugins}))

    def installed(self):
        return c.load_installed(c.load_json(str(self.record)))

    def env(self):
        env = os.environ.copy()
        env.update(self.env_overrides())
        return env


@pytest.fixture
def world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)
