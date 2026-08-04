from evileye.api.core.config_validation import (
    NumericValidator,
    PathValidator,
    list_sections,
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
