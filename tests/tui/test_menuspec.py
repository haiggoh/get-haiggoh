#!/usr/bin/env python3
"""Task 6 contract: menu-spec v1 validate/build_argv/menu_for + Back item.

Usage: python3 -m pytest tests/tui/test_menuspec.py -q
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from get_haiggoh_tui import menuspec as ms  # noqa: E402
from get_haiggoh_tui.inventory import Row  # noqa: E402

FIX = ROOT / "tests" / "tui" / "fixtures"


def load_fixture(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def row_with_menu(installed, menu):
    return Row(name="tool", section="tool", mark="💸", description="d", adds="a",
               installed=installed, latest=installed, status="current" if installed else "missing",
               diagnostic=None, menu=menu, tool={"name": "tool"})


class _R:
    def __init__(self, rc, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


class FakeExec:
    def __init__(self, rc=0, out=""):
        self.calls = []
        self.rc, self.out = rc, out

    def __call__(self, argv, **kw):
        self.calls.append(list(argv))
        return _R(self.rc, self.out)


class ValidateTests(unittest.TestCase):
    def test_valid_fixture_passes(self):
        self.assertEqual(ms.validate(load_fixture("menu-spec-valid.json")), [])

    def test_bad_version_fails(self):
        errs = ms.validate(load_fixture("menu-spec-bad-version.json"))
        self.assertTrue(any("menu_spec" in e for e in errs), errs)

    def test_placeholder_without_prompt_fails(self):
        errs = ms.validate(load_fixture("menu-spec-bad-placeholder-no-prompt.json"))
        self.assertTrue(any("amount" in e for e in errs), errs)

    def test_prompt_without_placeholder_fails(self):
        errs = ms.validate(load_fixture("menu-spec-bad-prompt-no-placeholder.json"))
        self.assertTrue(any("amount" in e for e in errs), errs)

    def test_choice_without_choices_fails(self):
        errs = ms.validate(load_fixture("menu-spec-bad-choice-no-choices.json"))
        self.assertTrue(any("choice" in e.lower() for e in errs), errs)


class BuildArgvTests(unittest.TestCase):
    def test_build_argv_no_shell_join(self):
        action = {"argv": ["cost-tracker", "cap", "{amount}"]}
        out = ms.build_argv(action, {"amount": "a; rm -rf ~"})
        self.assertEqual(out, ["cost-tracker", "cap", "a; rm -rf ~"],
                         "the answer must stay ONE argv element, never shell-joined")

    def test_whole_token_placeholders_only(self):
        action = {"argv": ["echo", "prefix-{x}", "{y}"]}
        out = ms.build_argv(action, {"x": "1", "y": "2"})
        self.assertEqual(out, ["echo", "prefix-{x}", "2"],
                         "embedded placeholders are not substituted")


class MenuForTests(unittest.TestCase):
    def test_never_probes_below_min_version(self):
        menu = {"argv": ["tool"], "spec_min_version": "0.2.0", "return_to_min_version": None}
        r = row_with_menu("0.1.0", menu)
        ex = FakeExec(rc=0, out=json.dumps(load_fixture("menu-spec-valid.json")))
        kind, payload = ms.menu_for(r, run=ex, which=lambda n: n)
        self.assertEqual(ex.calls, [], "ZERO probe calls below spec_min_version")
        self.assertEqual(kind, "legacy")
        self.assertEqual(payload, ["tool"])

    def test_never_probes_when_spec_min_null(self):
        menu = {"argv": ["tool"], "spec_min_version": None, "return_to_min_version": None}
        r = row_with_menu("9.9.9", menu)
        ex = FakeExec(rc=0, out=json.dumps(load_fixture("menu-spec-valid.json")))
        kind, _payload = ms.menu_for(r, run=ex, which=lambda n: n)
        self.assertEqual(ex.calls, [])
        self.assertEqual(kind, "legacy")

    def test_spec_when_supported_and_valid(self):
        menu = {"argv": ["tool"], "spec_min_version": "0.2.0", "return_to_min_version": "0.3.0"}
        r = row_with_menu("0.2.5", menu)
        ex = FakeExec(rc=0, out=json.dumps(load_fixture("menu-spec-valid.json")))
        kind, payload = ms.menu_for(r, run=ex, which=lambda n: n)
        self.assertEqual(kind, "spec")
        self.assertIsInstance(payload, dict)
        self.assertEqual(ex.calls, [["tool", "--menu-spec"]])

    def test_legacy_when_spec_json_invalid(self):
        menu = {"argv": ["tool"], "spec_min_version": "0.2.0", "return_to_min_version": None}
        r = row_with_menu("0.2.0", menu)
        ex = FakeExec(rc=0, out='{"menu_spec": 99}')
        kind, payload = ms.menu_for(r, run=ex, which=lambda n: n)
        self.assertEqual(kind, "legacy")
        self.assertEqual(payload, ["tool"])

    def test_return_to_only_when_supported(self):
        menu = {"argv": ["tool"], "spec_min_version": None, "return_to_min_version": "0.3.0"}
        r = row_with_menu("0.3.1", menu)
        _kind, payload = ms.menu_for(r, run=FakeExec(), which=lambda n: n)
        self.assertEqual(payload, ["tool", "--return-to", "get-haiggoh"])
        r_old = row_with_menu("0.2.9", menu)
        _kind, payload_old = ms.menu_for(r_old, run=FakeExec(), which=lambda n: n)
        self.assertEqual(payload_old, ["tool"], "no --return-to below return_to_min_version")

    def test_no_menu_returns_none(self):
        r = row_with_menu("1.0.0", None)
        self.assertEqual(ms.menu_for(r, run=FakeExec(), which=lambda n: n), ("none", None))


class BackTests(unittest.TestCase):
    def test_back_is_last(self):
        spec = load_fixture("menu-spec-valid.json")
        actions = ms.actions_with_back(spec)
        self.assertEqual(actions[-1]["label"], ms.BACK_LABEL)
        self.assertEqual(len(actions), len(spec["actions"]) + 1)
        self.assertEqual(ms.BACK_LABEL, "👨🏻‍💻 Back to Get Haiggoh")


if __name__ == "__main__":
    unittest.main()
