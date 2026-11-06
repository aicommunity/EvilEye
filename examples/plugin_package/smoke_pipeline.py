"""Run after installing this example package into the EvilEye environment."""

import time

import numpy as np

from evileye.controller.services.pipeline_service import PipelineService
from evileye.core.frame import Frame
from evileye.pipelines.pipeline_surveillance import PipelineSurveillance


def _run_surveillance_detector_smoke(mode, execution_mode):
    legacy_items = [
        {
            "module_id": "example/add-label",
            "execution_mode": "thread",
            "source_ids": [7],
            "label": "baseline",
        }
    ]
    extension_items = [
        {
            "module_id": "example/add-label",
            "execution_mode": execution_mode,
            "source_ids": [7],
            "label": "external",
        }
    ]
    pipeline = PipelineSurveillance()
    params = pipeline._normalize_pipeline_params(
        {
            "detectors": legacy_items,
            "modules": {
                "detectors": {"mode": mode, "items": extension_items}
            },
        }
    )
    pipeline._init_detectors(params["detectors"])
    stage = pipeline.processors[-1]
    frame = Frame()
    frame.source_id = 7
    frame.frame_id = 1
    frame.frame_version = 4
    frame.image = np.zeros((16, 16, 3), dtype=np.uint8)
    expected = {"external"} if mode == "replace" else {"baseline", "external"}
    results = []

    try:
        stage.start()
        for detector in stage.processors:
            if not detector.is_ready(15):
                raise RuntimeError(
                    f"example detector failed to start ({execution_mode})"
                )
        stage.process([({}, frame)])
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            results.extend(stage.process(None))
            labels = {
                item[0].get("plugin_label")
                for item in results
                if isinstance(item, (list, tuple))
                and len(item) >= 2
                and isinstance(item[0], dict)
            }
            if expected.issubset(labels):
                break
            time.sleep(0.005)
        if not expected.issubset(labels):
            raise AssertionError(
                f"{mode}/{execution_mode} returned labels {labels!r}"
            )
        for item in results:
            if (
                isinstance(item, (list, tuple))
                and len(item) >= 2
                and item[0].get("plugin_label") in expected
            ):
                if item[1].image is None or item[1].image.shape != (16, 16, 3):
                    raise AssertionError(
                        "detector did not preserve the shared frame payload"
                    )
                if item[1].frame_version != 4:
                    raise AssertionError("detector changed frame metadata")
    finally:
        stage.stop()
        stage.release()


def main():
    params = {
        "factory_marker": "from-dependencies",
        "marker": "external-package",
    }
    service = PipelineService()
    pipeline = service.create_pipeline(
        "example/marker-pipeline",
        pipeline_params=params,
    )
    if pipeline.marker != "from-dependencies":
        raise AssertionError("PipelineDependencies were not passed to the factory")

    service.initialize_pipeline(pipeline, params)
    try:
        service.start_pipeline()
        result = pipeline.process()
        expected = {"marker": "external-package", "sequence": 1}
        if result != expected:
            raise AssertionError(f"unexpected pipeline result: {result!r}")
    finally:
        service.stop_pipeline()
        service.release_pipeline()

    for mode in ("extend", "replace"):
        for execution_mode in ("thread", "process"):
            _run_surveillance_detector_smoke(mode, execution_mode)
    print("custom pipeline and Surveillance detector lifecycle passed")


if __name__ == "__main__":
    main()
