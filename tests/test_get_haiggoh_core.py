import json
import os
import tempfile

import get_haiggoh_core as c


def test_resolve_marketplace_json_path_reads_install_location():
    known = {"haiggoh": {"source": {"source": "github", "repo": "haiggoh/get-haiggoh"},
                          "installLocation": "/fake/marketplaces/haiggoh"}}
    assert c.resolve_marketplace_json_path(known, "haiggoh") == \
        "/fake/marketplaces/haiggoh/.claude-plugin/marketplace.json"


def test_resolve_marketplace_json_path_missing_marketplace_returns_none():
    assert c.resolve_marketplace_json_path({}, "haiggoh") is None


def test_load_json_returns_empty_dict_on_missing_file():
    assert c.load_json("/definitely/does/not/exist.json") == {}


def test_load_json_returns_empty_dict_on_malformed_json():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{not valid json")
        path = f.name
    try:
        assert c.load_json(path) == {}
    finally:
        os.remove(path)


def test_load_json_parses_valid_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"a": 1}, f)
        path = f.name
    try:
        assert c.load_json(path) == {"a": 1}
    finally:
        os.remove(path)


def test_load_marketplace_entries_returns_plugins_list():
    data = {"name": "haiggoh", "plugins": [{"name": "waypoints", "source": {}}]}
    assert c.load_marketplace_entries(data) == [{"name": "waypoints", "source": {}}]


def test_load_marketplace_entries_missing_plugins_key_returns_empty():
    assert c.load_marketplace_entries({}) == []


def test_load_installed_filters_by_marketplace_suffix():
    data = {"plugins": {
        "waypoints@haiggoh": [{"version": "0.1.7", "gitCommitSha": "abc123"}],
        "some-other@othermarket": [{"version": "1.0.0", "gitCommitSha": "zzz"}],
    }}
    out = c.load_installed(data)
    assert out == {"waypoints": {"version": "0.1.7", "gitCommitSha": "abc123"}}


def test_load_installed_missing_gitCommitSha_defaults_to_none():
    data = {"plugins": {"waypoints@haiggoh": [{"version": "0.1.7"}]}}
    out = c.load_installed(data)
    assert out["waypoints"]["gitCommitSha"] is None


def test_load_installed_empty_plugins_returns_empty():
    assert c.load_installed({}) == {}


def test_entry_repo_url_extracts_url_source():
    entry = {"name": "waypoints", "source": {"source": "url", "url": "https://github.com/haiggoh/waypoints.git"}}
    assert c.entry_repo_url(entry) == "https://github.com/haiggoh/waypoints.git"


def test_entry_repo_url_returns_none_for_dot_slash_source():
    entry = {"name": "self", "source": "./"}
    assert c.entry_repo_url(entry) is None


def test_entry_repo_url_returns_none_for_missing_source():
    assert c.entry_repo_url({"name": "x"}) is None


def test_load_skip_list_returns_empty_dict_on_missing_file():
    assert c.load_skip_list("/definitely/does/not/exist.json") == {}


def test_save_and_load_skip_list_roundtrip(tmp_path):
    path = str(tmp_path / "skip.json")
    c.save_skip_list(path, {"waypoints": "install"})
    assert c.load_skip_list(path) == {"waypoints": "install"}


def test_save_skip_list_creates_parent_dir(tmp_path):
    path = str(tmp_path / "nested" / "skip.json")
    c.save_skip_list(path, {"x": "update"})
    assert os.path.exists(path)


def _catalog():
    return [
        {"name": "get-haiggoh", "source": {"source": "url", "url": "https://github.com/haiggoh/get-haiggoh.git"}},
        {"name": "waypoints", "source": {"source": "url", "url": "https://github.com/haiggoh/waypoints.git"}},
        {"name": "measure-twice", "source": {"source": "url", "url": "https://github.com/haiggoh/measure-twice.git"}},
    ]


def test_compute_missing_excludes_self_and_installed():
    installed = {"waypoints": {"version": "0.1.7", "gitCommitSha": "abc"}}
    missing = c.compute_missing(_catalog(), installed, self_name="get-haiggoh")
    assert missing == ["measure-twice"]


def test_compute_missing_empty_when_all_installed():
    installed = {"waypoints": {}, "measure-twice": {}}
    assert c.compute_missing(_catalog(), installed, self_name="get-haiggoh") == []


def test_compute_outdated_flags_sha_mismatch():
    installed = {"waypoints": {"version": "0.1.6", "gitCommitSha": "old-sha"},
                 "measure-twice": {"version": "0.1.0", "gitCommitSha": "current-sha"}}
    remote_shas = {"waypoints": "new-sha", "measure-twice": "current-sha"}
    outdated = c.compute_outdated(_catalog(), installed, remote_shas, self_name="get-haiggoh")
    assert outdated == [{"name": "waypoints", "installed_sha": "old-sha", "remote_sha": "new-sha"}]


def test_compute_outdated_skips_not_installed():
    installed = {}
    remote_shas = {"waypoints": "new-sha", "measure-twice": "sha2"}
    assert c.compute_outdated(_catalog(), installed, remote_shas, self_name="get-haiggoh") == []


def test_compute_outdated_skips_unresolvable_remote_sha():
    installed = {"waypoints": {"gitCommitSha": "old-sha"}}
    remote_shas = {"waypoints": None}  # ls-remote failed -- never claim outdated from a failure
    assert c.compute_outdated(_catalog(), installed, remote_shas, self_name="get-haiggoh") == []


def test_compute_outdated_excludes_self():
    installed = {"get-haiggoh": {"gitCommitSha": "old"}}
    remote_shas = {"get-haiggoh": "new"}
    assert c.compute_outdated(_catalog(), installed, remote_shas, self_name="get-haiggoh") == []


def test_filter_missing_by_skip_drops_install_and_both_scopes():
    missing = ["a", "b", "c"]
    skip = {"a": "install", "b": "both", "c": "update"}
    assert c.filter_missing_by_skip(missing, skip) == ["c"]


def test_filter_outdated_by_skip_drops_update_and_both_scopes():
    outdated = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
    skip = {"a": "update", "b": "both", "c": "install"}
    assert c.filter_outdated_by_skip(outdated, skip) == [{"name": "c"}]


def test_filter_catalog_by_selection_no_filters_returns_unchanged():
    catalog = _catalog()
    assert c.filter_catalog_by_selection(catalog) == catalog


def test_filter_catalog_by_selection_by_names():
    catalog = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
    assert c.filter_catalog_by_selection(catalog, names=["a", "c"]) == [
        {"name": "a"}, {"name": "c"}]


def test_filter_catalog_by_selection_unknown_name_drops_silently():
    catalog = [{"name": "a"}, {"name": "b"}]
    assert c.filter_catalog_by_selection(catalog, names=["nope"]) == []


def test_filter_catalog_by_selection_by_category():
    catalog = [{"name": "a", "category": "x"}, {"name": "b", "category": "y"}]
    assert c.filter_catalog_by_selection(catalog, category="y") == [
        {"name": "b", "category": "y"}]


def test_filter_catalog_by_selection_names_and_category_and():
    catalog = [{"name": "a", "category": "x"}, {"name": "b", "category": "y"},
               {"name": "c", "category": "y"}]
    assert c.filter_catalog_by_selection(catalog, names=["a", "b"], category="y") == [
        {"name": "b", "category": "y"}]


def test_should_refresh_true_when_stamp_missing(tmp_path):
    assert c.should_refresh(str(tmp_path / "nope"), "2026-07-16") is True


def test_should_refresh_false_when_stamp_matches_today(tmp_path):
    path = str(tmp_path / "stamp")
    c.mark_refreshed(path, "2026-07-16")
    assert c.should_refresh(path, "2026-07-16") is False


def test_should_refresh_true_when_stamp_is_a_prior_day(tmp_path):
    path = str(tmp_path / "stamp")
    c.mark_refreshed(path, "2026-07-15")
    assert c.should_refresh(path, "2026-07-16") is True


def test_format_nudge_empty_when_nothing_to_report():
    assert c.format_nudge([], []) == ""


def test_format_nudge_lists_missing_plugins():
    b = c.format_nudge(["measure-twice"], [])
    assert "measure-twice" in b
    assert "get-haiggoh" in b  # points at the skill/plugin name to resolve it


def test_format_nudge_lists_outdated_plugins():
    b = c.format_nudge([], [{"name": "waypoints", "installed_sha": "a", "remote_sha": "b"}])
    assert "waypoints" in b


def test_format_nudge_lists_both_sections_when_both_present():
    b = c.format_nudge(["measure-twice"], [{"name": "waypoints", "installed_sha": "a", "remote_sha": "b"}])
    assert "measure-twice" in b and "waypoints" in b


# --- Option B: SHA cache (save_refresh_state / load_cached_shas) ---

def test_save_refresh_state_marks_date_so_should_refresh_is_false(tmp_path):
    path = str(tmp_path / "stamp")
    c.save_refresh_state(path, "2026-07-20", {"waypoints": "abc"})
    assert c.should_refresh(path, "2026-07-20") is False
    assert c.should_refresh(path, "2026-07-21") is True  # next day re-refreshes


def test_save_and_load_cached_shas_roundtrip(tmp_path):
    path = str(tmp_path / "stamp")
    shas = {"waypoints": "deadbeef", "measure-twice": None}
    c.save_refresh_state(path, "2026-07-20", shas)
    assert c.load_cached_shas(path) == shas


def test_load_cached_shas_empty_when_missing_or_no_key(tmp_path):
    assert c.load_cached_shas(str(tmp_path / "nope")) == {}
    # a legacy stamp written by mark_refreshed has no remote_shas key
    legacy = str(tmp_path / "legacy")
    c.mark_refreshed(legacy, "2026-07-20")
    assert c.load_cached_shas(legacy) == {}


def test_cached_shas_feed_compute_outdated(tmp_path):
    # End-to-end of the off-day path: cached shas -> compute_outdated flags the drifted one.
    path = str(tmp_path / "stamp")
    c.save_refresh_state(path, "2026-07-20", {"waypoints": "remote1", "measure-twice": "same"})
    catalog = [{"name": "waypoints"}, {"name": "measure-twice"}]
    installed = {"waypoints": {"gitCommitSha": "local0"},
                 "measure-twice": {"gitCommitSha": "same"}}
    outdated = c.compute_outdated(catalog, installed, c.load_cached_shas(path), "get-haiggoh")
    assert [o["name"] for o in outdated] == ["waypoints"]
