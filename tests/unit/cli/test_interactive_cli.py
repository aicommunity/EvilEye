from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import click
import pytest
import typer
from typer.testing import CliRunner

from evileye.cli import app
from evileye.cli_interactive import (
    COMMAND_POLICIES,
    GROUP_MENU_POLICIES,
    InteractiveInputError,
    NON_INTERACTIVE_ENV,
    interactive_available,
    strip_non_interactive_flags,
)

runner = CliRunner()


def _leaf_commands(group: click.Group, prefix: tuple[str, ...] = ()):
    for name, command in group.commands.items():
        path = (*prefix, name)
        if isinstance(command, click.Group):
            yield from _leaf_commands(command, path)
        else:
            yield " ".join(path), command


def test_every_registered_cli_leaf_has_an_explicit_policy():
    root = typer.main.get_command(app)
    leaves = dict(_leaf_commands(root))

    assert set(leaves) == set(COMMAND_POLICIES)
    assert leaves["tls-cert"].hidden
    assert not COMMAND_POLICIES["tls-cert"].menu
    assert {
        path for path, command in leaves.items() if not command.hidden
    } == {path for path, policy in COMMAND_POLICIES.items() if policy.menu}

    groups = {
        name
        for name, command in root.commands.items()
        if isinstance(command, click.Group)
    }
    assert groups == set(GROUP_MENU_POLICIES)
    assert all(GROUP_MENU_POLICIES.values())
    root_context = click.Context(root, info_name="evileye")
    import evileye.cli_interactive as interactive

    visible = {name for name, _ in interactive._public_commands(root_context)}
    assert visible == {name for name, command in root.commands.items() if not command.hidden}


def test_non_interactive_flags_are_removed_regardless_of_position():
    parsed, forced = strip_non_interactive_flags(
        ["--nit", "pipeline", "restart", "--no-interactive", "configs/a.json"]
    )
    assert parsed == ["pipeline", "restart", "configs/a.json"]
    assert forced


def test_hidden_tls_cert_is_rejected_in_tty(monkeypatch):
    import evileye.cli_interactive as interactive
    import evileye.utils.tls_cert as tls_cert_module

    monkeypatch.setattr(interactive, "interactive_available", lambda: True)
    generate = Mock()
    monkeypatch.setattr(tls_cert_module, "generate_minica_leaf", generate)

    result = runner.invoke(app, ["tls-cert"])

    assert result.exit_code == 2
    assert "only in non-interactive mode" in result.output
    generate.assert_not_called()


def test_hidden_tls_cert_remains_available_with_noninteractive_flag(monkeypatch):
    import evileye.cli_interactive as interactive
    import evileye.utils.tls_cert as tls_cert_module

    monkeypatch.setattr(interactive, "interactive_available", lambda: False)
    generate = Mock(return_value={"server_crt": Path("certs/server.crt"), "ca_crt": Path("certs/ca.crt")})
    monkeypatch.setattr(tls_cert_module, "generate_minica_leaf", generate)

    result = runner.invoke(app, ["--nit", "tls-cert"])

    assert result.exit_code == 0, result.output
    generate.assert_called_once()


def test_non_interactive_environment_overrides_a_tty(monkeypatch):
    class Tty:
        @staticmethod
        def isatty() -> bool:
            return True

    monkeypatch.setattr("evileye.cli_interactive.sys.stdin", Tty())
    monkeypatch.setenv(NON_INTERACTIVE_ENV, "1")
    assert not interactive_available()


def test_root_menu_dispatches_selected_registered_command(monkeypatch):
    import evileye.cli_interactive as interactive

    monkeypatch.setattr(interactive, "interactive_available", lambda: True)
    dispatch = Mock(return_value=0)
    monkeypatch.setattr(interactive, "_dispatch", dispatch)
    monkeypatch.setattr(interactive.Prompt, "ask", lambda *args, **kwargs: "1")

    result = runner.invoke(app, [])

    assert result.exit_code == 0, result.output
    assert "Команды EvilEye" in result.output
    assert "tls-cert" not in result.output
    dispatch.assert_called_once()
    assert dispatch.call_args.args[0] == ["status"]


def test_group_menu_dispatches_through_existing_cli_entrypoint(monkeypatch):
    import evileye.cli_interactive as interactive

    monkeypatch.setattr(interactive, "interactive_available", lambda: True)
    monkeypatch.setattr(interactive.Prompt, "ask", lambda *args, **kwargs: "1")
    subprocess_run = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(interactive.subprocess, "run", subprocess_run)

    result = runner.invoke(app, ["pipeline"])

    assert result.exit_code == 0, result.output
    assert "Команды: pipeline" in result.output
    args = subprocess_run.call_args.args[0]
    assert args[-2:] == ["pipeline", "status"]
    assert subprocess_run.call_args.kwargs["env"][interactive.MENU_SELECTION_ENV] == "1"


def test_every_registered_group_opens_its_own_menu(monkeypatch):
    import evileye.cli_interactive as interactive

    monkeypatch.setattr(interactive, "interactive_available", lambda: True)
    monkeypatch.setattr(interactive.Prompt, "ask", lambda *args, **kwargs: "0")
    subprocess_run = Mock()
    monkeypatch.setattr(interactive.subprocess, "run", subprocess_run)

    for group_name in GROUP_MENU_POLICIES:
        result = runner.invoke(app, [group_name])
        assert result.exit_code == 0, (group_name, result.output)
        assert f"Команды: {group_name}" in result.output
    subprocess_run.assert_not_called()


@pytest.mark.parametrize(
    "command_path",
    [path.split() for path, policy in COMMAND_POLICIES.items() if policy.menu],
)
def test_every_public_leaf_routes_to_its_existing_cli_command(monkeypatch, command_path):
    import evileye.cli_interactive as interactive

    monkeypatch.setattr(interactive, "_menu_arguments", lambda _path: [])
    monkeypatch.setattr(interactive, "confirm_action", lambda _message, default=False: True)
    subprocess_run = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(interactive.subprocess, "run", subprocess_run)

    result = interactive._dispatch(command_path)

    assert result == 0
    args = subprocess_run.call_args.args[0]
    assert args[-len(command_path):] == command_path
    assert subprocess_run.call_args.kwargs["env"][interactive.MENU_SELECTION_ENV] == "1"


@pytest.mark.parametrize(
    "command_path,message",
    [
        (path.split(), policy.confirmation)
        for path, policy in COMMAND_POLICIES.items()
        if policy.menu and policy.confirmation
    ],
)
def test_declining_each_menu_confirmation_prevents_dispatch(monkeypatch, command_path, message):
    import evileye.cli_interactive as interactive

    monkeypatch.setattr(interactive, "_menu_arguments", lambda _path: [])
    confirm = Mock(return_value=False)
    monkeypatch.setattr(interactive, "confirm_action", confirm)
    subprocess_run = Mock()
    monkeypatch.setattr(interactive.subprocess, "run", subprocess_run)

    assert interactive._dispatch(command_path) == 0
    confirm.assert_called_once_with(message, default=False)
    subprocess_run.assert_not_called()


def test_declining_menu_confirmation_has_no_side_effect(monkeypatch):
    import evileye.cli_interactive as interactive

    monkeypatch.setattr(interactive.Confirm, "ask", lambda *args, **kwargs: False)
    print_message = Mock()
    monkeypatch.setattr(interactive.console, "print", print_message)
    subprocess_run = Mock()
    monkeypatch.setattr(interactive.subprocess, "run", subprocess_run)

    assert interactive._dispatch(["service", "stop"]) == 0
    assert "Действие отменено." in str(print_message.call_args)
    subprocess_run.assert_not_called()


def test_tty_plugin_create_prompts_for_missing_name(tmp_path: Path, monkeypatch):
    import evileye.cli_interactive as interactive

    monkeypatch.setattr(interactive, "interactive_available", lambda: True)
    monkeypatch.setattr(interactive, "prompt_text", lambda label, default=None: "interactive-plugin")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["plugin", "create"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "interactive-plugin" / "pyproject.toml").is_file()


def test_tty_config_create_prompts_for_name_and_required_source_count(tmp_path: Path, monkeypatch):
    import evileye.cli_interactive as interactive
    import evileye.controller.controller as controller_module

    class FakeController:
        def get_available_pipeline_classes(self):
            return ["PipelineSurveillance"]

        def create_config(self, **kwargs):
            return kwargs

    monkeypatch.setattr(controller_module, "Controller", FakeController)
    monkeypatch.setattr(interactive, "interactive_available", lambda: True)
    monkeypatch.setattr(interactive, "prompt_text", lambda label, default=None: "guided-config")
    monkeypatch.setattr(interactive, "prompt_integer", lambda label, default: 2)
    monkeypatch.setattr(interactive, "prompt_choice", lambda label, choices, default=None: choices[0][0])
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["create"])

    assert result.exit_code == 0, result.output
    created = json.loads((tmp_path / "configs" / "guided-config.json").read_text())
    assert created["num_sources"] == 2
    assert created["pipeline_class"] == "PipelineSurveillance"


def test_complete_create_invocation_does_not_open_a_wizard(tmp_path: Path, monkeypatch):
    import evileye.cli_interactive as interactive
    import evileye.controller.controller as controller_module

    class FakeController:
        def create_config(self, **kwargs):
            return kwargs

    monkeypatch.setattr(controller_module, "Controller", FakeController)
    monkeypatch.setattr(interactive, "interactive_available", lambda: True)
    monkeypatch.setattr(interactive, "prompt_text", Mock(side_effect=AssertionError("unexpected prompt")))
    monkeypatch.setattr(interactive, "prompt_integer", Mock(side_effect=AssertionError("unexpected prompt")))
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["create", "direct-config", "--sources", "2"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "configs" / "direct-config.json").is_file()


def test_prompt_helpers_report_eof_and_interrupt_as_cancelled(monkeypatch):
    import evileye.cli_interactive as interactive

    monkeypatch.setattr(interactive.Prompt, "ask", Mock(side_effect=EOFError))
    with pytest.raises(InteractiveInputError, match="Ввод отменён"):
        interactive.prompt_text("Имя")

    monkeypatch.setattr(interactive.Confirm, "ask", Mock(side_effect=KeyboardInterrupt))
    with pytest.raises(InteractiveInputError, match="Ввод отменён"):
        interactive.confirm_action("Подтвердить?")


def test_help_and_non_tty_incomplete_calls_do_not_open_menus(monkeypatch):
    import evileye.cli_interactive as interactive

    monkeypatch.setattr(interactive, "interactive_available", lambda: False)
    help_result = runner.invoke(app, ["--help"])
    assert help_result.exit_code == 0
    assert "Usage:" in help_result.output

    root_result = runner.invoke(app, [])
    assert root_result.exit_code == 2
    assert "Usage:" in root_result.output

    group_result = runner.invoke(app, ["pipeline"])
    assert group_result.exit_code == 2
    assert "Usage:" in group_result.output

    validate_result = runner.invoke(app, ["validate"])
    assert validate_result.exit_code == 2
    assert "Configuration path is required" in validate_result.output

    plugin_result = runner.invoke(app, ["plugin", "create"])
    assert plugin_result.exit_code == 2
    assert "Plugin name is required" in plugin_result.output

    prod_result = runner.invoke(app, ["prod", "init"])
    assert prod_result.exit_code == 2
    assert "Production config path is required" in prod_result.output

    stop_result = runner.invoke(app, ["pipeline", "stop"])
    assert stop_result.exit_code == 1
    assert "--config" in stop_result.output


def test_validate_prompts_for_missing_config_only_when_interactive(tmp_path: Path, monkeypatch):
    import evileye.cli as cli
    import evileye.cli_interactive as interactive

    config = tmp_path / "valid.json"
    config.write_text(json.dumps({"pipeline": {"sources": [{"source": "video", "camera": 0}]}}))
    monkeypatch.setattr(interactive, "interactive_available", lambda: True)
    monkeypatch.setattr(interactive, "prompt_config_path", lambda label="Конфигурация": str(config))
    monkeypatch.setattr(cli, "validate_config", lambda _config: None)
    monkeypatch.setattr(cli.ConfigValidator, "validate_full_config", lambda _self, _config: (True, ""))

    result = runner.invoke(app, ["validate"])

    assert result.exit_code == 0, result.output
    assert "valid!" in result.output


def test_pipeline_stop_uses_interactive_target_picker(tmp_path: Path, monkeypatch):
    import evileye.cli_interactive as interactive
    from evileye.stack_control import StopResult

    monkeypatch.setattr(interactive, "interactive_available", lambda: True)
    monkeypatch.setattr(
        interactive,
        "prompt_pipeline_stop_target",
        lambda: ("configs/current.json", False),
    )
    stop = Mock(return_value=StopResult(stopped_pids=[321]))
    monkeypatch.setattr("evileye.stack_control.stop_pipelines", stop)

    result = runner.invoke(app, ["pipeline", "stop"])

    assert result.exit_code == 0, result.output
    assert "321" in result.output
    assert stop.call_args.kwargs["config"] == "configs/current.json"
    assert stop.call_args.kwargs["stop_all"] is False


@pytest.mark.parametrize("operation", ["start", "restart"])
def test_pipeline_start_and_restart_prompt_only_after_resolution_fails(monkeypatch, operation):
    import evileye.cli_interactive as interactive
    import evileye.stack_control as stack_control

    monkeypatch.setattr(interactive, "interactive_available", lambda: True)
    monkeypatch.setattr(interactive, "prompt_config_path", lambda label="": "configs/selected.json")
    require = Mock(side_effect=[FileNotFoundError("no implicit config"), "configs/selected.json"])
    monkeypatch.setattr(stack_control, "require_pipeline_config", require)
    spawn = stack_control.SpawnResult(pid=321, mode="managed", config_path="configs/selected.json")
    monkeypatch.setattr(stack_control, "pipeline_start", Mock(return_value=spawn))
    monkeypatch.setattr(stack_control, "pipeline_restart", Mock(return_value=spawn))
    monkeypatch.setattr(stack_control, "should_use_managed_launch", lambda _path: True)

    result = runner.invoke(app, ["pipeline", operation])

    assert result.exit_code == 0, result.output
    assert require.call_count == 2
    assert require.call_args_list[-1].kwargs["explicit"] == "configs/selected.json"


def test_prod_init_prompts_for_config_and_propagates_noninteractive_to_children(
    monkeypatch,
):
    import evileye.cli_interactive as interactive
    import evileye.cli_commands.prod as prod

    run = Mock()
    monkeypatch.setattr(prod.subprocess, "run", run)
    monkeypatch.setattr("evileye.site_profile.save_profile", Mock())
    monkeypatch.setattr("evileye.watchdog_native.install_watchdog", Mock())
    monkeypatch.setattr(interactive, "interactive_available", lambda: True)
    monkeypatch.setattr(interactive, "prompt_config_path", lambda label="": "configs/prod.json")

    result = runner.invoke(app, ["--nit", "prod", "init"])

    assert result.exit_code == 0, result.output
    assert run.call_count == 2
    assert all(call.kwargs["env"][NON_INTERACTIVE_ENV] == "1" for call in run.call_args_list)
    assert run.call_args_list[1].args[0][-1].replace(chr(92), "/") == "configs/prod.json"


@pytest.mark.parametrize(
    "arguments",
    [
        ["--nit", "pipeline", "stop", "--all"],
        ["pipeline", "stop", "--all", "--no-interactive"],
    ],
)
def test_main_strips_opt_out_anywhere_and_propagates_environment(monkeypatch, arguments):
    import sys
    import os
    import evileye.cli as cli

    observed: dict[str, object] = {}

    def fake_app(*, args):
        observed["args"] = args
        observed["env"] = os.environ.get(NON_INTERACTIVE_ENV)

    monkeypatch.setattr(cli, "app", fake_app)
    monkeypatch.setattr(sys, "argv", ["evileye", *arguments])
    monkeypatch.delenv(NON_INTERACTIVE_ENV, raising=False)

    cli.main()

    assert observed["args"] == ["pipeline", "stop", "--all"]
    assert observed["env"] == "1"
    assert NON_INTERACTIVE_ENV not in os.environ
