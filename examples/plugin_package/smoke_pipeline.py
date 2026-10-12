"""Run after installing this example package into the EvilEye environment."""

from evileye.controller.services.pipeline_service import PipelineService


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
        print(result)
    finally:
        service.stop_pipeline()
        service.release_pipeline()


if __name__ == "__main__":
    main()
