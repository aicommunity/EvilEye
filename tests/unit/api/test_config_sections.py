from evileye.api.core.config_validation import list_sections, validate_config


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


def test_list_sections():
    secs = list_sections({"sources": [], "detectors": [], "custom": {}})
    assert "sources" in secs
    assert "detectors" in secs
