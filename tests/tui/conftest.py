"""Ship-gate contract (Task 1): with GET_HAIGGOH_REQUIRE_TEXTUAL=1 a TUI pytest run
must have textual importable and zero skipped tests, or the session fails — so a
green gate can never mean "every pilot silently import-skipped".

The gate command lives in rtc-ship.json (test_cmd): the full suite under the pipx
pytest, then the TUI pilots under the TUI venv python with this switch on.
"""
import os
import sys
from typing import Mapping

import pytest

REQUIRE_ENV = "GET_HAIGGOH_REQUIRE_TEXTUAL"


def required_violation(env: Mapping[str, str], textual_ok: bool, skipped: int) -> str | None:
    """The violation message when the requirement is on and violated, else None."""
    if env.get(REQUIRE_ENV) != "1":
        return None
    if not textual_ok:
        return (
            f"{REQUIRE_ENV}=1 is set but 'import textual' failed under {sys.executable}; "
            "run the TUI tests with ~/.local/share/get-haiggoh/tui-venv/bin/python -m pytest"
        )
    if skipped:
        return (
            f"{REQUIRE_ENV}=1 is set and the run ended with {skipped} skipped — "
            "a skipped pilot is a failed receipt, never a pass"
        )
    return None


def _textual_ok() -> bool:
    try:
        import textual  # noqa: F401

        return True
    except ImportError:
        return False


def pytest_configure(config):
    if os.environ.get(REQUIRE_ENV) == "1":
        msg = required_violation(os.environ, _textual_ok(), 0)
        if msg:
            raise pytest.UsageError(msg)


def pytest_sessionfinish(session, exitstatus):
    if os.environ.get(REQUIRE_ENV) != "1":
        return
    tr = session.config.pluginmanager.get_plugin("terminalreporter")
    skipped = len(tr.stats.get("skipped", [])) if tr is not None else 0
    msg = required_violation(os.environ, _textual_ok(), skipped)
    if msg:
        if tr is not None:
            tr.write_sep("=", msg)
        session.exitstatus = 1
