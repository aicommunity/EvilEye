from evileye.core.config_validator import ConfigValidator


def test_pipeline_module_extension_config_is_validated_without_pydantic():
    validator = ConfigValidator()
    validator._pydantic_available = False

    assert validator.validate_pipeline_config(
        {
            "modules": {
                "detectors": {
                    "mode": "extend",
                    "items": [{"module_id": "vendor/custom-detector"}],
                }
            }
        }
    ) == (True, None)


def test_pipeline_module_extension_reports_invalid_mode_and_group():
    validator = ConfigValidator()
    validator._pydantic_available = False

    assert validator.validate_pipeline_config(
        {"modules": {"detectors": {"mode": "append", "items": []}}}
    ) == (False, "modules.detectors.mode must be 'replace' or 'extend'")
    assert validator.validate_pipeline_config(
        {"modules": {"events": {"mode": "extend", "items": []}}}
    ) == (False, "Unsupported PipelineSurveillance module group: events")


def test_pipeline_module_extension_rejects_invalid_envelopes():
    validator = ConfigValidator()
    validator._pydantic_available = False

    assert validator.validate_pipeline_config({"modules": []}) == (
        False,
        "Pipeline modules must be an object",
    )
    assert validator.validate_pipeline_config(
        {"modules": {"sources": {"mode": "replace", "items": {}}}}
    ) == (False, "modules.sources.items must be a list")
