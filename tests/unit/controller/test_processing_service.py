from evileye.controller.processing_service import ProcessingService


def test_should_log_resource_stats():
    assert ProcessingService.should_log_resource_stats(0, 5.0, now_ts=100.0) is True
    assert ProcessingService.should_log_resource_stats(95.0, 5.0, now_ts=100.0) is True
    assert ProcessingService.should_log_resource_stats(96.0, 5.0, now_ts=100.0) is False
    assert ProcessingService.should_log_resource_stats(98.0, 5.0, now_ts=100.0) is False
    assert ProcessingService.should_log_resource_stats(0, 0) is False


def test_compute_loop_sleep_seconds():
    assert ProcessingService.compute_loop_sleep_seconds(30.0, 0.01) > 0
    assert ProcessingService.compute_loop_sleep_seconds(None, 0.05) == 0.03


def test_collect_processing_frames_tuple_and_fallback():
    vis = [(0, "img0"), "img1"]
    fallback = ["fb"]
    frames = ProcessingService.collect_processing_frames(vis, fallback)
    assert frames == ["img0", "img1"]
    assert ProcessingService.collect_processing_frames([], fallback) == ["fb"]
