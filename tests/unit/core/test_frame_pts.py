from evileye.core.frame_pts import media_pts_sec, valid_pts_ns


def test_valid_pts_ns_rejects_clock_none():
    assert valid_pts_ns(0)
    assert valid_pts_ns(1_000_000_000)
    assert not valid_pts_ns(None)
    assert not valid_pts_ns(0xFFFFFFFFFFFFFFFF)


def test_media_pts_sec_relative_to_first():
    assert abs(media_pts_sec(3_500_000_000, 1_000_000_000) - 2.5) < 1e-9
