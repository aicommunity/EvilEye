"""Tests that plugin imports do not pull sibling runtimes into workers."""

import subprocess
import sys
from pathlib import Path


def test_importing_rfdetr_module_does_not_import_sibling_model_runtimes():
    repo_root = Path(__file__).resolve().parents[3]
    script = (
        "import importlib, sys; "
        "importlib.import_module('evileye.object_detector.object_detection_rfdetr'); "
        "assert 'ultralytics' not in sys.modules; "
        "assert 'supervision' not in sys.modules; "
        "assert 'matplotlib.pyplot' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_core_package_import_does_not_eagerly_load_pipeline_plugins():
    repo_root = Path(__file__).resolve().parents[3]
    script = (
        "import evileye.core, sys; "
        "assert 'evileye.pipelines.pipeline_surveillance' not in sys.modules; "
        "assert 'evileye.object_detector.object_detection_yolo' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_rfdetr_rejects_unsafe_thread_execution_mode():
    import pytest

    from evileye.core.base_class import EvilEyeBase
    from evileye.core.plugins import PluginError
    from evileye.object_detector import register_builtin_modules

    register_builtin_modules()
    adapter = EvilEyeBase.create_instance("ObjectDetectorRfdetr")
    with pytest.raises(PluginError, match="does not support execution_mode='thread'"):
        adapter.set_params(
            module_id="ObjectDetectorRfdetr",
            execution_mode="thread",
        )
