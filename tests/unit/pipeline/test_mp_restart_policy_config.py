from evileye.core.mp_control import parse_mp_restart_policy


def test_parse_restart_policy_defaults():
    restart, codes = parse_mp_restart_policy(None, default_restart_on_exit=True)
    assert restart is True
    assert -15 in codes


def test_parse_restart_policy_from_config():
    params = {
        "mp_restart_on_exit": False,
        "mp_no_restart_exit_codes": [-15, -9, 0],
    }
    restart, codes = parse_mp_restart_policy(params, default_restart_on_exit=True)
    assert restart is False
    assert codes == {-15, -9, 0}
