from boomi_release import manifest as mf


def comp(cid, name, ctype="process"):
    return {"componentId": cid, "name": name, "type": ctype}


def entry(cid, name, version, package_id, test=None):
    e = {"componentId": cid, "name": name, "type": "process", "packageVersion": version, "packageId": package_id}
    if test:
        e["testHarnessId"] = test
    return e


def test_latest_package_uses_created_date_not_version_string():
    packages = [
        {"packageId": "a", "packageVersion": "9.0", "createdDate": "2026-01-01T00:00:00Z", "branchName": "main"},
        {"packageId": "b", "packageVersion": "1.10", "createdDate": "2026-03-01T00:00:00Z", "branchName": "main"},
        {"packageId": "c", "packageVersion": "2.0", "createdDate": "2026-02-01T00:00:00Z", "branchName": "main"},
    ]
    assert mf.pick_latest_package(packages)["packageId"] == "b"


def test_latest_package_ignores_other_branches_and_deleted():
    packages = [
        {"packageId": "main-old", "createdDate": "2026-01-01T00:00:00Z", "branchName": "main"},
        {"packageId": "feature", "createdDate": "2026-05-01T00:00:00Z", "branchName": "feature/x"},
        {"packageId": "deleted", "createdDate": "2026-06-01T00:00:00Z", "branchName": "main", "deleted": True},
        {"packageId": "legacy", "createdDate": "2025-12-01T00:00:00Z"},  # pre Branch & Merge = main
    ]
    assert mf.pick_latest_package(packages)["packageId"] == "main-old"
    assert mf.pick_latest_package(packages, "feature/x")["packageId"] == "feature"
    assert mf.pick_latest_package([], "main") is None


def test_harness_matching_by_suffix():
    components = [comp("1", "Order Sync"), comp("2", "Order Sync - Test"), comp("3", "Lonely - Test"), comp("4", "Other")]
    harnesses, ids = mf.match_test_harnesses(components)
    assert {k: v["componentId"] for k, v in harnesses.items()} == {"1": "2"}
    assert ids == {"2"}
    assert mf.match_test_harnesses(components, "") == ({}, set())


def test_diff_added_updated_removed():
    old = {"components": [entry("a", "Keep", "1.0", "p1"), entry("b", "Bump", "1.0", "p2"), entry("c", "Gone", "2.0", "p3")]}
    new = {"components": [entry("a", "Keep", "1.0", "p1"), entry("b", "Bump", "1.1", "p4", test="h"), entry("d", "New", "1.0", "p5")]}
    rows = {r[1]: r for r in mf.diff(old, new)}
    assert rows["Bump"] == ("updated", "Bump", "process", "1.0", "1.1", True)
    assert rows["New"][0] == "added"
    assert rows["Gone"][0] == "removed"
    assert "Keep" not in rows
    body = mf.diff_markdown(old, new)
    assert "⬆️ Updated | Bump | process | 1.0 | 1.1 | ✅" in body
    assert "1 component(s) unchanged" in body


def test_diff_treats_same_version_new_package_as_update():
    old = {"components": [entry("a", "X", "1.0", "p1")]}
    new = {"components": [entry("a", "X", "1.0", "p2")]}
    assert mf.diff(old, new)[0][0] == "updated"


def test_previous_deployment():
    history = [
        {"packageId": "p3", "packageVersion": "1.2", "active": True, "version": 4},
        {"packageId": "p3", "packageVersion": "1.2", "active": False, "version": 3},
        {"packageId": "p1", "packageVersion": "1.0", "active": False, "version": 2},
    ]
    active, previous = mf.previous_deployment(history)
    assert active["packageId"] == "p3" and previous["packageId"] == "p1"
    assert mf.previous_deployment([]) == (None, None)
    assert mf.previous_deployment(history[:1])[1] is None


def test_rollback_after_rollback_goes_further_back_not_forward():
    # 1.2 → 1.3 → 1.5 → rollback to 1.3 (active). The next rollback must restore 1.2, not 1.5.
    history = [
        {"packageId": "v13", "packageVersion": "1.3", "active": True, "version": 9},
        {"packageId": "v15", "packageVersion": "1.5", "active": False, "version": 8},
        {"packageId": "v13", "packageVersion": "1.3", "active": False, "version": 5},
        {"packageId": "v12", "packageVersion": "1.2", "active": False, "version": 4},
    ]
    assert mf.previous_deployment(history)[1]["packageVersion"] == "1.2"
    # A fresh bad release rolls back to the release before it.
    fresh = [{"packageId": "v14", "packageVersion": "1.4", "active": True, "version": 10}] + history
    assert mf.previous_deployment(fresh)[1]["packageVersion"] == "1.3"


def test_config_values_resolve_secrets_from_environment():
    resolved = mf.resolve_config_values({"URL": "https://x", "PASSWORD": "$env:ERP_PASSWORD"}, {"ERP_PASSWORD": "s3cret"})
    assert resolved == [("URL", "https://x", "https://x"), ("PASSWORD", "s3cret", "•••• (from secret)")]


def test_missing_secret_is_an_error_not_an_empty_value():
    import pytest
    with pytest.raises(ValueError, match="ERP_PASSWORD"):
        mf.resolve_config_values({"PASSWORD": "$env:ERP_PASSWORD"}, {})


def test_load_missing_manifest_is_empty(tmp_path):
    assert mf.load(tmp_path / "nope.json") == {"components": []}


def test_save_sorts_and_round_trips(tmp_path):
    path = tmp_path / "release" / "release.json"
    mf.save(str(path), {"components": [entry("b", "beta", "1", "p"), entry("a", "Alpha", "1", "q")]})
    assert [c["name"] for c in mf.load(path)["components"]] == ["Alpha", "beta"]
    assert path.read_text(encoding="utf-8").endswith("\n")
