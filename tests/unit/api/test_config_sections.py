from evileye.api.core.config_validation import (
    NumericValidator,
    PathValidator,
    get_by_path,
    list_sections,
    list_studio_tabs,
    set_by_path,
    split_path,
    validate_config,
)


def test_validate_config_ok():
    result = validate_config({"sources": [], "detectors": [{"model": "m.pt", "roi": [[]]}]})
    assert result["ok"] is True


def test_validate_config_errors():
    result = validate_config({"sources": "bad", "detectors": "x"})
    assert result["ok"] is False
    assert result["errors"]


def test_validate_conf_range():
    result = validate_config({"detectors": [{"model": "m.pt", "conf": 1.5}]})
    assert result["ok"] is False
    assert any("conf" in e for e in result["errors"])


def test_path_and_numeric_validators():
    assert PathValidator("model", file_types=[".pt"]).validate("a.pt")
    assert not PathValidator("model", file_types=[".pt"]).validate("a.bin")
    assert NumericValidator("port", min_value=1, max_value=65535, integer=True).validate(5432)
    assert not NumericValidator("port", min_value=1, max_value=65535, integer=True).validate(0)


def test_list_sections():
    secs = list_sections({"sources": [], "detectors": [], "custom": {}})
    assert "sources" in secs
    assert "detectors" in secs


def test_get_set_by_path_roundtrip():
    body: dict = {"pipeline": {"sources": [{"source": "a"}]}, "server": {"port": 1}}
    assert get_by_path(body, "pipeline.sources") == [{"source": "a"}]
    set_by_path(body, "pipeline.detectors", [{"model": "m.pt"}])
    assert get_by_path(body, "pipeline.detectors")[0]["model"] == "m.pt"
    set_by_path(body, "record.enabled", True)
    assert body["record"]["enabled"] is True


def test_split_path_rejects_traversal():
    try:
        split_path("a/../b")
        assert False, "expected ValueError"
    except ValueError:
        pass
    try:
        split_path("a..b")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_list_studio_tabs_order_and_fallback():
    nested = {
        "pipeline": {"sources": [], "detectors": [], "trackers": []},
        "controller": {},
        "server": {},
        "database": {},
    }
    tabs = list_studio_tabs(nested)
    ids = [t["id"] for t in tabs]
    assert ids.index("sources") < ids.index("detectors") < ids.index("controller") < ids.index("server")
    assert tabs[ids.index("sources")]["path"] == "pipeline.sources"

    flat = {"sources": [], "detectors": []}
    flat_tabs = list_studio_tabs(flat)
    by_id = {t["id"]: t["path"] for t in flat_tabs}
    assert by_id["sources"] == "sources"
    assert by_id["detectors"] == "detectors"
