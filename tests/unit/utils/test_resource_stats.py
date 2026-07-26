from evileye.utils.resource_stats import collect_process_resource_stats, format_resource_stats_line


def test_collect_process_resource_stats_current_pid():
    stats = collect_process_resource_stats()
    assert stats is not None
    assert stats.pid is not None
    assert stats.rss_mb is not None and stats.rss_mb > 0


def test_format_resource_stats_line():
    from evileye.utils.resource_stats import ProcessResourceStats

    stats = ProcessResourceStats(pid=1, rss_mb=10.5, num_threads=2, num_fds=3, open_files=4)
    line = format_resource_stats_line("test", stats, extra_suffix=" tail")
    assert "ResourceStats[test]" in line
    assert "rss_mb=10.500" in line
    assert line.endswith(" tail")
