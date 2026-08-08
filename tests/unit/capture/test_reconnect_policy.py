from evileye.capture.reconnect_policy import allow_noframes_reconnect, reconnect_wait_sec


def test_allow_noframes_reconnect_first_time():
    assert allow_noframes_reconnect(0.0, 100.0, 45.0) is True


def test_allow_noframes_reconnect_inside_cooldown():
    assert allow_noframes_reconnect(100.0, 120.0, 45.0) is False


def test_allow_noframes_reconnect_after_cooldown():
    assert allow_noframes_reconnect(100.0, 150.0, 45.0) is True


def test_reconnect_wait_attempt_zero_immediate():
    assert reconnect_wait_sec(0, initial_delay_sec=8, backoff_step_sec=6, max_delay_sec=60) == 0.0


def test_reconnect_wait_attempt_zero_with_min_first():
    assert (
        reconnect_wait_sec(
            0,
            initial_delay_sec=8,
            backoff_step_sec=6,
            max_delay_sec=60,
            min_first_backoff_sec=3.0,
        )
        == 3.0
    )


def test_reconnect_wait_increases_with_attempts():
    w1 = reconnect_wait_sec(1, initial_delay_sec=8, backoff_step_sec=6, max_delay_sec=60)
    w2 = reconnect_wait_sec(2, initial_delay_sec=8, backoff_step_sec=6, max_delay_sec=60)
    assert w1 == 8.0
    assert w2 == 14.0
