"""ROI config editor API tests."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from evileye.api.routes import config_editors


@pytest.fixture
def client(tmp_path, monkeypatch):
    cfg = tmp_path / "test.json"
    cfg.write_text(
        """{
  "pipeline": {
    "sources": [{"source_ids": [0], "source_names": ["Cam1"], "frame_width": 1920, "frame_height": 1080}],
    "detectors": [{"source_ids": [0], "roi": [[[100, 50, 200, 100]]]}]
  }
}""",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_editors, "configs_dir", lambda: tmp_path)
    app = FastAPI()
    app.include_router(config_editors.router)
    return TestClient(app)


def test_get_roi_returns_normalized_xyxy(client):
    res = client.get("/api/v1/configs/test.json/sources/0/roi")
    assert res.status_code == 200
    data = res.json()
    rois = data["rois"]
    assert len(rois) == 1
    assert rois[0][0] == pytest.approx(100 / 1920, rel=1e-3)
    assert data["rois_pixel"] == [[100.0, 50.0, 200.0, 100.0]]
    assert data["coord_ref"] == {"w": 1920, "h": 1080}
    assert data["display_rois"] == data["rois"]


def test_config_editors_imports():
    from evileye.api.routes import config_editors as ce

    assert ce.get_roi is not None


@patch.object(config_editors, "_find_runtime_id_for_config", return_value=1)
@patch.object(config_editors, "_apply_roi_runtime", return_value=True)
def test_put_roi_applies_live(mock_apply, mock_run, client):
    ui_roi = [[0.1, 0.1, 0.3, 0.3]]
    res = client.put("/api/v1/configs/test.json/sources/0/roi", json={"rois": ui_roi})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "updated"
    assert data["applied_live"] is True
    assert data["restart_required"] is False
    mock_apply.assert_called_once()
    stored = client.get("/api/v1/configs/test.json/sources/0/roi").json()["rois"]
    assert len(stored) == 1


@patch.object(config_editors, "_find_runtime_id_for_config", return_value=None)
def test_put_roi_restart_when_no_run(mock_run, client):
    res = client.put("/api/v1/configs/test.json/sources/0/roi", json={"rois": []})
    assert res.status_code == 200
    data = res.json()
    assert data["restart_required"] is True
    assert data.get("applied_live") is False


@patch.object(config_editors, "_find_runtime_id_for_config", return_value=None)
def test_put_roi_uses_coord_ref(mock_run, client):
    ui_roi = [[1790 / 1920, 0, (1790 + 500) / 1920, 400 / 1080]]
    res = client.put(
        "/api/v1/configs/test.json/sources/0/roi",
        json={"rois": ui_roi, "coord_ref": {"w": 1920, "h": 1080}},
    )
    assert res.status_code == 200
    stored = client.get("/api/v1/configs/test.json/sources/0/roi").json()["rois_pixel"]
    assert stored[0][0] == 1790.0
    assert stored[0][1] == 0.0
    assert stored[0][2] in (500.0, 501.0)
    assert stored[0][3] in (400.0, 401.0)
