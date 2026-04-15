from evileye.pipelines.pipeline_surveillance import PipelineSurveillance


def test_get_latest_objects_results_uses_strict_latest_mode():
    pipeline = PipelineSurveillance()
    pipeline.results_selection_mode = "strict_latest"
    pipeline.add_result({"sources": [("old", 1)]})
    pipeline.add_result({"sources": []})

    results = pipeline.get_latest_objects_results()
    assert results == []


def test_get_latest_objects_results_keeps_sticky_non_empty_mode():
    pipeline = PipelineSurveillance()
    pipeline.results_selection_mode = "sticky_non_empty"
    pipeline.add_result({"sources": [("old", 1)]})
    pipeline.add_result({"sources": []})

    results = pipeline.get_latest_objects_results()
    assert results == [("old", 1)]
