import json

from evileye.utils.json_io import load_json, save_json_atomic


def test_save_and_load_json_atomic(tmp_path):
    path = tmp_path / "cfg.json"
    data = {"pipeline": {"sources": [{"camera": "a.mp4"}]}}
    assert save_json_atomic(path, data) is True
    loaded = load_json(path)
    assert loaded == data


def test_load_json(tmp_path):
    path = tmp_path / "x.json"
    path.write_text('{"k": 1}', encoding="utf-8")
    assert load_json(path) == {"k": 1}
