from evileye.pipelines.pipeline_surveillance import PipelineSurveillance


def _pipeline_with_mc_final() -> PipelineSurveillance:
    pipeline = PipelineSurveillance()
    pipeline.set_processor_params(
        "mc_trackers",
        [{"enable": True, "source_ids": [0, 1]}],
    )
    pipeline._final_results_name = "mc_trackers"
    return pipeline


def test_get_latest_objects_results_uses_strict_latest_mode():
    pipeline = PipelineSurveillance()
    pipeline._final_results_name = "sources"
    pipeline.results_selection_mode = "strict_latest"
    pipeline.add_result({"sources": [("old", 1)]})
    pipeline.add_result({"sources": []})

    results = pipeline.get_latest_objects_results()
    assert results == []


def test_get_latest_objects_results_keeps_sticky_non_empty_mode():
    pipeline = PipelineSurveillance()
    pipeline._final_results_name = "sources"
    pipeline.results_selection_mode = "sticky_non_empty"
    pipeline.add_result({"sources": [("old", 1)]})
    pipeline.add_result({"sources": []})

    results = pipeline.get_latest_objects_results()
    assert results == [("old", 1)]


def test_strict_latest_final_section_only():
    pipeline = _pipeline_with_mc_final()
    pipeline.results_selection_mode = "strict_latest"
    pipeline.add_result({"mc_trackers": [], "trackers": [("track", 0)]})

    assert pipeline.get_latest_objects_results() == []


def test_sticky_mc_only_not_trackers():
    pipeline = _pipeline_with_mc_final()
    pipeline.results_selection_mode = "sticky_non_empty"
    # Results queue maxsize=2; keep both snapshots in one dict per tick.
    pipeline.add_result(
        {"mc_trackers": [("mc", 1)], "trackers": [("track", 0)]}
    )
    pipeline.add_result(
        {"mc_trackers": [], "trackers": [("track", 1)]}
    )

    assert pipeline.get_latest_objects_results() == [("mc", 1)]


def test_objects_do_not_fall_back_to_trackers_when_mc_empty():
    pipeline = _pipeline_with_mc_final()
    pipeline.set_processor_params("trackers", [{"source_ids": [0]}])
    pipeline.results_selection_mode = "sticky_non_empty"
    pipeline.add_result({"mc_trackers": [], "trackers": [("tr", 1)]})

    assert pipeline.get_latest_objects_results() == []


def test_viz_falls_back_to_sources_not_trackers_when_mc_empty():
    pipeline = _pipeline_with_mc_final()
    pipeline.set_processor_params("trackers", [{"source_ids": [0]}])
    pipeline.results_selection_mode = "sticky_non_empty"
    pipeline.add_result(
        {"mc_trackers": [], "trackers": [("tr_frame", 1)], "sources": [("src", 0)]}
    )

    assert pipeline.get_latest_visualization_frames() == [("src", 0)]


def test_viz_falls_back_to_sources_when_final_empty():
    pipeline = _pipeline_with_mc_final()
    pipeline.results_selection_mode = "sticky_non_empty"
    pipeline.add_result({"mc_trackers": [], "sources": [("src", 0)]})
    pipeline.add_result({"mc_trackers": [], "sources": [("src", 2)]})

    assert pipeline.get_latest_objects_results() == []
    assert pipeline.get_latest_visualization_frames() == [("src", 2)]
