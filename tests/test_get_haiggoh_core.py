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
    assert out == {"waypoints": {"version": "0.1.7", "installPath": None}}


def test_load_installed_reads_version_and_install_path():
    data = {"plugins": {"waypoints@haiggoh": [
        {"version": "0.1.7", "installPath": "/cache/haiggoh/waypoints/0.1.7"}]}}
    out = c.load_installed(data)
    assert out["waypoints"] == {"version": "0.1.7",
                                 "installPath": "/cache/haiggoh/waypoints/0.1.7"}


def test_load_installed_ignores_the_never_updated_git_commit_sha():
    """gitCommitSha is stale for every plugin updated at least once, so nothing may read it --
    a caller that can see the field is a caller that can compare against it again."""
    data = {"plugins": {"waypoints@haiggoh": [{"version": "0.1.7", "gitCommitSha": "abc123"}]}}
    assert "gitCommitSha" not in c.load_installed(data)["waypoints"]


def test_load_installed_missing_version_defaults_to_none():
    data = {"plugins": {"waypoints@haiggoh": [{"installPath": "/somewhere"}]}}
    assert c.load_installed(data)["waypoints"]["version"] is None


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
    installed = {"waypoints": {"version": "0.1.7"}}
    missing = c.compute_missing(_catalog(), installed, self_name="get-haiggoh")
    assert missing == ["measure-twice"]


def test_compute_missing_empty_when_all_installed():
    installed = {"waypoints": {}, "measure-twice": {}}
    assert c.compute_missing(_catalog(), installed, self_name="get-haiggoh") == []


# --- plugin_manifest_url / parse_version / remote_is_newer ---

def test_plugin_manifest_url_from_https_git_url():
    assert c.plugin_manifest_url("https://github.com/haiggoh/waypoints.git") == \
        "https://raw.githubusercontent.com/haiggoh/waypoints/HEAD/.claude-plugin/plugin.json"


def test_plugin_manifest_url_accepts_forms_without_dot_git_and_ssh():
    expected = ("https://raw.githubusercontent.com/haiggoh/waypoints/HEAD"
                "/.claude-plugin/plugin.json")
    for url in ("https://github.com/haiggoh/waypoints",
                "https://github.com/haiggoh/waypoints/",
                "http://github.com/haiggoh/waypoints.git",
                "git@github.com:haiggoh/waypoints.git",
                "ssh://git@github.com/haiggoh/waypoints.git"):
        assert c.plugin_manifest_url(url) == expected, url


def test_plugin_manifest_url_returns_none_for_a_non_github_url():
    assert c.plugin_manifest_url("https://gitlab.com/haiggoh/waypoints.git") is None
    assert c.plugin_manifest_url(None) is None


def test_parse_version_reads_dotted_numeric_and_tolerates_v_prefix():
    assert c.parse_version("0.5.1") == (0, 5, 1)
    assert c.parse_version("v1.2") == (1, 2)
    assert c.parse_version("0.4.0-rc1") == (0, 4, 0)
    assert c.parse_version("not-a-version") is None
    assert c.parse_version(None) is None


def test_remote_is_newer_only_when_remote_is_ahead():
    assert c.remote_is_newer("0.5.0", "0.5.1") is True
    assert c.remote_is_newer("0.5.1", "0.5.1") is False
    assert c.remote_is_newer("0.5.2", "0.5.1") is False  # local ahead of remote is not outdated
    assert c.remote_is_newer("0.9.0", "0.10.0") is True  # numeric, not lexicographic


def test_remote_is_newer_pads_unequal_length_versions():
    assert c.remote_is_newer("0.4", "0.4.0") is False
    assert c.remote_is_newer("0.4", "0.4.1") is True


def test_remote_is_newer_falls_silent_when_either_side_is_unknown():
    assert c.remote_is_newer("0.5.0", None) is False
    assert c.remote_is_newer(None, "0.5.0") is False
    assert c.remote_is_newer("", "0.5.0") is False


def test_remote_is_newer_degrades_to_inequality_for_unorderable_versions():
    assert c.remote_is_newer("main", "0.5.0") is True
    assert c.remote_is_newer("main", "main") is False


# --- compute_outdated (version comparison, NOT sha comparison) ---

def test_compute_outdated_flags_a_newer_published_version():
    installed = {"waypoints": {"version": "0.1.6"}, "measure-twice": {"version": "0.1.0"}}
    remote_versions = {"waypoints": "0.2.0", "measure-twice": "0.1.0"}
    outdated = c.compute_outdated(_catalog(), installed, remote_versions, self_name="get-haiggoh")
    assert outdated == [{"name": "waypoints", "installed_version": "0.1.6",
                         "remote_version": "0.2.0"}]


def test_compute_outdated_reports_nothing_when_versions_match():
    """THE regression this fix exists for: sha-comparison nagged for 9 of 9 plugins whose
    installed version already equalled the published one, because gitCommitSha is never
    rewritten. Matching versions must produce an empty list."""
    installed = {"waypoints": {"version": "0.5.1"}, "measure-twice": {"version": "0.2.0"}}
    remote_versions = {"waypoints": "0.5.1", "measure-twice": "0.2.0"}
    assert c.compute_outdated(_catalog(), installed, remote_versions, "get-haiggoh") == []


def test_compute_outdated_ignores_a_same_version_push():
    """A push that does not bump plugin.json has nowhere new to land -- the install path is
    keyed on the version -- so reporting it would be a nag no update could ever satisfy."""
    installed = {"waypoints": {"version": "0.5.1"}}
    assert c.compute_outdated(_catalog(), installed, {"waypoints": "0.5.1"}, "get-haiggoh") == []


def test_compute_outdated_ignores_a_local_version_ahead_of_the_remote():
    installed = {"waypoints": {"version": "0.6.0"}}
    assert c.compute_outdated(_catalog(), installed, {"waypoints": "0.5.1"}, "get-haiggoh") == []


def test_compute_outdated_skips_not_installed():
    installed = {}
    remote_versions = {"waypoints": "9.9.9", "measure-twice": "9.9.9"}
    assert c.compute_outdated(_catalog(), installed, remote_versions, self_name="get-haiggoh") == []


def test_compute_outdated_skips_unresolvable_remote_version():
    installed = {"waypoints": {"version": "0.1.6"}}
    remote_versions = {"waypoints": None}  # fetch failed -- never claim outdated from a failure
    assert c.compute_outdated(_catalog(), installed, remote_versions, self_name="get-haiggoh") == []


def test_compute_outdated_skips_when_the_installed_version_is_unknown():
    installed = {"waypoints": {"version": None}}
    assert c.compute_outdated(_catalog(), installed, {"waypoints": "0.5.1"}, "get-haiggoh") == []


def test_compute_outdated_excludes_self():
    installed = {"get-haiggoh": {"version": "0.1.0"}}
    remote_versions = {"get-haiggoh": "9.9.9"}
    assert c.compute_outdated(_catalog(), installed, remote_versions, self_name="get-haiggoh") == []


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


def test_format_nudge_lists_outdated_plugins_with_both_versions():
    b = c.format_nudge([], [{"name": "waypoints", "installed_version": "0.5.0",
                             "remote_version": "0.5.1"}])
    assert "0.5.0 -> 0.5.1" in b
    assert "waypoints" in b


def test_format_nudge_lists_both_sections_when_both_present():
    b = c.format_nudge(["measure-twice"], [{"name": "waypoints", "installed_version": "0.5.0",
                                            "remote_version": "0.5.1"}])
    assert "measure-twice" in b and "waypoints" in b


# --- Option B: version cache (save_refresh_state / load_cached_versions) ---

def test_save_refresh_state_marks_date_so_should_refresh_is_false(tmp_path):
    path = str(tmp_path / "stamp")
    c.save_refresh_state(path, "2026-07-20", {"waypoints": "0.5.1"})
    assert c.should_refresh(path, "2026-07-20") is False
    assert c.should_refresh(path, "2026-07-21") is True  # next day re-refreshes


def test_save_and_load_cached_versions_roundtrip(tmp_path):
    path = str(tmp_path / "stamp")
    versions = {"waypoints": "0.5.1", "measure-twice": None}
    c.save_refresh_state(path, "2026-07-20", versions)
    assert c.load_cached_versions(path) == versions


def test_load_cached_versions_empty_when_missing_or_no_key(tmp_path):
    assert c.load_cached_versions(str(tmp_path / "nope")) == {}
    # a legacy stamp written by mark_refreshed has no remote_versions key
    legacy = str(tmp_path / "legacy")
    c.mark_refreshed(legacy, "2026-07-20")
    assert c.load_cached_versions(legacy) == {}


def test_load_cached_versions_ignores_a_stamp_holding_the_old_sha_cache(tmp_path):
    """A stamp written by <=0.3.4 carries `remote_shas`. Reading those as versions would
    compare a sha against a version and nag for everything, so they are ignored: the nudge
    stays silent for the rest of that day and the next daily refresh writes the new key."""
    path = str(tmp_path / "legacy-shas")
    with open(path, "w") as f:
        json.dump({"date": "2026-07-20", "remote_shas": {"waypoints": "deadbeef"}}, f)
    assert c.load_cached_versions(path) == {}


def test_cached_versions_feed_compute_outdated(tmp_path):
    # End-to-end of the off-day path: cached versions -> compute_outdated flags the drifted one.
    path = str(tmp_path / "stamp")
    c.save_refresh_state(path, "2026-07-20", {"waypoints": "0.6.0", "measure-twice": "0.2.0"})
    catalog = [{"name": "waypoints"}, {"name": "measure-twice"}]
    installed = {"waypoints": {"version": "0.5.1"},
                 "measure-twice": {"version": "0.2.0"}}
    outdated = c.compute_outdated(catalog, installed, c.load_cached_versions(path), "get-haiggoh")
    assert [o["name"] for o in outdated] == ["waypoints"]
