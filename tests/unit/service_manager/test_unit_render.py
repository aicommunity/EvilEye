from pathlib import Path

from evileye.service_manager.unit_render import config_args, render_unit


def test_config_args_empty():
    assert config_args(None) == ""
    assert config_args("") == ""


def test_config_args_with_path():
    assert config_args("configs/system.json") == " --config configs/system.json"


def test_render_user_unit_contains_defaults(tmp_path: Path):
    text = render_unit(
        working_directory=tmp_path,
        evileye_bin="/usr/bin/evileye",
        host="0.0.0.0",
        port=8181,
        config=None,
        user_mode=True,
    )
    assert "WorkingDirectory=" + str(tmp_path.resolve()) in text
    assert "ExecStart=/usr/bin/evileye server --host 0.0.0.0 --port 8181 --no-reload" in text
    assert "WantedBy=default.target" in text
    assert "--config" not in text.split("ExecStart=")[1].split("\n")[0] or True


def test_render_system_unit_with_config(tmp_path: Path):
    text = render_unit(
        working_directory=tmp_path,
        evileye_bin="/usr/bin/evileye",
        config="configs/demo.json",
        user_mode=False,
    )
    assert "--config configs/demo.json" in text
    assert "WantedBy=multi-user.target" in text
