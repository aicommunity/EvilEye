from scripts.measure_poly_e2e_fps import RuntimeStatsSampler


def test_runtime_stats_sampler_reports_peaks_counter_deltas_and_recovery():
    baseline = {
        "degraded": False,
        "modules": {
            "detectors/example/slow": {
                "execution_mode": "thread",
                "worker_running": True,
                "input_queue_size": 0,
                "output_queue_size": 0,
                "in_flight": 0,
                "input_queue_dropped": 2,
                "input_queue_rejected": 3,
                "degraded": False,
            }
        },
    }
    sampler = RuntimeStatsSampler(baseline)
    sampler.observe(
        {
            "degraded": True,
            "modules": {
                "detectors/example/slow": {
                    "execution_mode": "thread",
                    "worker_running": True,
                    "input_queue_size": 2,
                    "output_queue_size": 1,
                    "in_flight": 3,
                    "input_queue_dropped": 4,
                    "input_queue_rejected": 3,
                    "degraded": True,
                }
            },
        }
    )
    sampler.observe(
        {
            "degraded": False,
            "modules": {
                "detectors/example/slow": {
                    "execution_mode": "thread",
                    "worker_running": True,
                    "input_queue_size": 1,
                    "output_queue_size": 0,
                    "in_flight": 1,
                    "input_queue_dropped": 5,
                    "input_queue_rejected": 4,
                    "degraded": False,
                }
            },
        }
    )

    summary = sampler.finish(
        {
            "degraded": False,
            "modules": {
                "detectors/example/slow": {
                    "execution_mode": "thread",
                    "worker_running": True,
                    "input_queue_size": 0,
                    "output_queue_size": 0,
                    "in_flight": 0,
                    "input_queue_dropped": 5,
                    "input_queue_rejected": 4,
                    "degraded": False,
                }
            },
        }
    )

    module = summary["modules"]["detectors/example/slow"]
    assert module["input_queue_depth_max"] == 2
    assert module["output_queue_depth_max"] == 1
    assert module["in_flight_max"] == 3
    assert module["input_queue_dropped"] == 3
    assert module["input_queue_rejected"] == 1
    assert module["degraded_seen"] is True
    assert module["degraded_at_end"] is False
    assert module["worker_running_at_end"] is True
    assert summary["pipeline_degraded_seen"] is True
    assert summary["pipeline_degraded_at_end"] is False
