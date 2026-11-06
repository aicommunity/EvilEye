from evileye.core.runtime_identity import event_health, process_identity, redact
from evileye.deploy_monitor.event_health import evaluate


def test_idle_pipeline_is_healthy_and_stalled_updates_are_not():
    stats = {'components': {
        'events_processor': {'worker_alive': True, 'last_success_at': 100},
        'events_controller': {'worker_alive': True, 'last_success_at': 100, 'detectors': {
            'zones': {'started': True, 'worker_running': True, 'updates_submitted': 0,
                      'updates_completed': 0, 'started_at': 1}}}}}
    assert event_health(stats, now=110) == []
    stats['components']['events_controller']['detectors']['zones']['updates_submitted'] = 1
    assert event_health(stats, now=110) == ['zones:updates_stalled']


def test_monitor_requires_three_stale_polls_and_resets_for_new_pid():
    payload = {'pid': 7, 'updated_at': 1, 'failures': []}
    state = {'pid': 7, 'first_seen_at': 1}
    for now in (40, 50):
        state, reason = evaluate(payload, 7, state, now)
        assert reason == ''
    state, reason = evaluate(payload, 7, state, 60)
    assert reason == 'heartbeat_stale'
    state, reason = evaluate(payload, 8, state, 70)
    assert reason == '' and state['streak'] == 0
    payload = {'pid': 8, 'updated_at': 71, 'failures': ['zones:worker_stopped']}
    assert evaluate(payload, 8, state, 71)[1] == 'zones:worker_stopped'


def test_native_capture_teardown_stall_is_reported_for_watchdog_recovery():
    stats = {'components': {'events_controller': {}, 'events_processor': {},
             'pipeline': {'module_instances': {'source/2': {
                 'capture_health': {'teardown_pending_since': 10}}}}}}
    assert event_health(stats, now=45) == ['source/2:native_teardown_stalled']


def test_secrets_are_redacted_and_effective_config_changes_identity_hash():
    value = redact({'password': 'hidden', 'error': 'Failed rtsp://user:pass@camera/path',
                    'config': {'session_secret': 'hidden'}})
    assert value['password'] == '[redacted]'
    assert 'user:pass' not in value['error']
    assert value['config']['session_secret'] == '[redacted]'
    assert process_identity({'a': 1})['config_sha256'] != process_identity({'a': 2})['config_sha256']
