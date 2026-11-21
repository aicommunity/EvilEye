"""Stage 2: plugin name safety (B3), operation bookkeeping (C4), catalog cache and disabling (B1)."""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from evileye.core import extension_builder
from evileye.core.plugin_scaffold import PluginScaffoldError, normalize_plugin_name


@pytest.mark.parametrize("name", ["pytest", "json", "os", "typing", "sys"])
def test_plugin_name_may_not_shadow_importable_or_stdlib_modules(name):
    with pytest.raises(PluginScaffoldError, match="shadow|standard library"):
        normalize_plugin_name(name)


def test_plugin_name_accepts_unused_names():
    assert normalize_plugin_name("my-new-plugin-xyz") == ("my-new-plugin-xyz", "my_new_plugin_xyz")


def test_plugin_name_allows_previous_scaffold_inside_site_plugin_directory(tmp_path, monkeypatch):
    package = tmp_path / "zz_site_plugin_demo"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(PluginScaffoldError, match="shadow"):
        normalize_plugin_name("zz-site-plugin-demo")
    assert normalize_plugin_name("zz-site-plugin-demo", allow_existing_under=tmp_path)[1] == "zz_site_plugin_demo"


def _record(index: int, status: str, tmp_path: Path) -> dict:
    archive = extension_builder._artifact_directory(tmp_path) / f"{index:08x}-0000.zip"
    archive.write_bytes(b"zip")
    return {
        "id": f"{index:08x}-0000",
        "status": status,
        "name": f"p{index}",
        "plugin_id": f"p{index}",
        "template": "processor",
        "created_at": index,
        "updated_at": float(index),
        "archive": str(archive),
    }


def test_operation_history_is_rotated_but_active_operations_are_kept(tmp_path):
    for index in range(1, 106):
        extension_builder._store_operation(_record(index, "completed", tmp_path), tmp_path)
    extension_builder._store_operation(_record(1000, "installing", tmp_path), tmp_path)
    extension_builder._store_operation(_record(0, "installing", tmp_path), tmp_path)  # oldest, but active

    removed = extension_builder.prune_plugin_operations(keep=100, root=tmp_path)

    directory = extension_builder._operation_directory(tmp_path)
    remaining = {path.stem for path in directory.glob("*.json")}
    assert removed == 5
    assert "00000000-0000" in remaining and "000003e8-0000" in remaining  # active ones survive
    assert "00000002-0000" not in remaining  # oldest finished ones removed
    assert not (extension_builder._artifact_directory(tmp_path) / "00000002-0000.zip").exists()
    assert (extension_builder._artifact_directory(tmp_path) / "00000069-0000.zip").exists()


def test_status_lock_serializes_updates_across_processes(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    extension_builder._store_operation(
        {"id": "00000001-0000", "status": "installing", "counter": 0, "updated_at": 1.0}, root
    )
    script = textwrap.dedent(
        """
        import sys
        from pathlib import Path
        from evileye.core import extension_builder as eb
        root = Path(sys.argv[1])
        for _ in range(25):
            with eb._status_lock(root):
                op = eb.get_plugin_operation("00000001-0000", root=root)
                op["counter"] += 1
                eb._store_operation(op, root)
        """
    )
    processes = [
        subprocess.Popen([sys.executable, "-c", script, str(root)], cwd=str(Path(__file__).resolve().parents[3]))
        for _ in range(4)
    ]
    assert [process.wait(timeout=120) for process in processes] == [0, 0, 0, 0]

    assert extension_builder.get_plugin_operation("00000001-0000", root=root)["counter"] == 100


def test_plugin_is_loaded_reports_unregistered_plugin():
    loaded, reason = extension_builder._plugin_is_loaded("definitely_not_a_plugin_xyz")
    assert loaded is False
    assert "not registered" in reason


def test_disabled_plugins_roundtrip_and_validation(tmp_path):
    assert extension_builder.list_disabled_plugins(root=tmp_path) == []

    result = extension_builder.set_plugin_disabled("sample-plugin", True, root=tmp_path)
    extension_builder.set_plugin_disabled("other", True, root=tmp_path)
    assert result["restart_required"] is True
    assert extension_builder.list_disabled_plugins(root=tmp_path) == ["other", "sample-plugin"]

    extension_builder.set_plugin_disabled("sample-plugin", False, root=tmp_path)
    assert extension_builder.list_disabled_plugins(root=tmp_path) == ["other"]

    state_file = tmp_path / "plugins" / ".evileye" / "disabled_plugins.json"
    assert json.loads(state_file.read_text(encoding="utf-8")) == ["other"]
    for bad in ("", "../x", "a b", "x" * 200):
        with pytest.raises(ValueError):
            extension_builder.set_plugin_disabled(bad, True, root=tmp_path)


def test_catalog_is_cached_until_invalidated(monkeypatch):
    calls = []

    def build():
        calls.append(1)
        return {"modules": [], "pipelines": []}

    monkeypatch.setattr(extension_builder, "_build_extension_catalog", build)
    extension_builder.invalidate_catalog_cache()
    try:
        first = extension_builder.extension_catalog()
        assert extension_builder.extension_catalog() is first
        assert len(calls) == 1
        extension_builder.invalidate_catalog_cache()
        extension_builder.extension_catalog()
        assert len(calls) == 2
    finally:
        extension_builder.invalidate_catalog_cache()


def test_catalog_reports_plugin_status():
    extension_builder.invalidate_catalog_cache()
    try:
        status = extension_builder.extension_catalog()["plugin_status"]
    finally:
        extension_builder.invalidate_catalog_cache()
    assert set(status) >= {"loaded", "failed", "disabled", "disabled_in_ui", "disabled_by_env"}
