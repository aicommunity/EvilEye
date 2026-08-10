from __future__ import annotations

import json
from pathlib import Path

from evileye.core.filelock import with_file_lock


def test_filelock_allows_nested_write(tmp_path):
    target = tmp_path / "store.json"
    target.write_text("{}", encoding="utf-8")
    with with_file_lock(target):
        data = json.loads(target.read_text(encoding="utf-8"))
        data["ok"] = True
        target.write_text(json.dumps(data), encoding="utf-8")
    assert json.loads(target.read_text(encoding="utf-8"))["ok"] is True
