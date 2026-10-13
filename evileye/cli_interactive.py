"""TTY-aware menus and prompts for the EvilEye command line."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import click
import typer
from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

NON_INTERACTIVE_ENV = "EVILEYE_NON_INTERACTIVE"
MENU_SELECTION_ENV = "EVILEYE_INTERACTIVE_SELECTION"
_META_FLAGS = {"--no-interactive", "--nit"}
console = Console()


@dataclass(frozen=True)
class CommandInteractionPolicy:
    """Explicit UI policy for a registered CLI leaf command."""

    menu: bool = True
    wizard: str | None = None
    confirmation: str | None = None


COMMAND_POLICIES: dict[str, CommandInteractionPolicy] = {
    "status": CommandInteractionPolicy(),
    "run": CommandInteractionPolicy(wizard="run"),
    "server": CommandInteractionPolicy(),
    "validate": CommandInteractionPolicy(wizard="config"),
    "list-configs": CommandInteractionPolicy(),
    "deploy": CommandInteractionPolicy(
        confirmation="Обновить файлы сайта и monitor? Некоторые служебные файлы будут перезаписаны."
    ),
    "watchdog-install": CommandInteractionPolicy(wizard="watchdog-config"),
    "watchdog-uninstall": CommandInteractionPolicy(confirmation="Удалить задачи watchdog?"),
    "watchdog-check": CommandInteractionPolicy(wizard="watchdog-check"),
    "watchdog-morning": CommandInteractionPolicy(),
    "deploy-samples": CommandInteractionPolicy(
        confirmation="Развернуть примеры? Существующие sample-конфигурации могут быть перезаписаны."
    ),
    "create": CommandInteractionPolicy(wizard="create"),
    "info": CommandInteractionPolicy(),
    "web check": CommandInteractionPolicy(),
    "web deps": CommandInteractionPolicy(),
    "web build": CommandInteractionPolicy(),
    "web refresh": CommandInteractionPolicy(confirmation="Пересобрать интерфейс и перезапустить веб-службу?"),
    "service install": CommandInteractionPolicy(wizard="service-install"),
    "service uninstall": CommandInteractionPolicy(confirmation="Удалить веб-службу?"),
    "service start": CommandInteractionPolicy(),
    "service stop": CommandInteractionPolicy(confirmation="Остановить веб-службу?"),
    "service restart": CommandInteractionPolicy(confirmation="Перезапустить веб-службу?"),
    "service status": CommandInteractionPolicy(),
    "pipeline status": CommandInteractionPolicy(),
    "pipeline stop": CommandInteractionPolicy(wizard="pipeline-stop"),
    "pipeline start": CommandInteractionPolicy(wizard="pipeline-config"),
    "pipeline restart": CommandInteractionPolicy(
        wizard="pipeline-config", confirmation="Перезапустить pipeline?"
    ),
    "plugin templates": CommandInteractionPolicy(),
    "plugin create": CommandInteractionPolicy(wizard="plugin-create"),
    "reload web": CommandInteractionPolicy(confirmation="Перезапустить веб-слой?"),
    "reload backend": CommandInteractionPolicy(confirmation="Перезапустить backend?"),
    "reload pipeline": CommandInteractionPolicy(
        wizard="pipeline-config", confirmation="Перезапустить pipeline?"
    ),
    "prod init": CommandInteractionPolicy(
        wizard="config",
        confirmation="Инициализировать production site и установить веб-службу?",
    ),
    "prod up": CommandInteractionPolicy(),
    "prod down": CommandInteractionPolicy(confirmation="Остановить production-стек?"),
    "prod restart": CommandInteractionPolicy(confirmation="Перезапустить production-стек?"),
    "dev server": CommandInteractionPolicy(),
    "tls-cert": CommandInteractionPolicy(menu=False),
}

GROUP_MENU_POLICIES = {
    "web": True,
    "service": True,
    "pipeline": True,
    "plugin": True,
    "reload": True,
    "prod": True,
    "dev": True,
}


class InteractiveInputError(RuntimeError):
    """Raised when an interactive prompt cannot receive user input."""


def strip_non_interactive_flags(argv: Sequence[str]) -> tuple[list[str], bool]:
    """Remove CLI policy flags from argv so they work before or after a command."""
    result: list[str] = []
    forced = False
    for token in argv:
        if token in _META_FLAGS:
            forced = True
        else:
            result.append(token)
    return result, forced


def non_interactive_forced() -> bool:
    if os.environ.get(NON_INTERACTIVE_ENV, "").strip().lower() in {
        "1", "true", "yes", "on"
    }:
        return True
    context = click.get_current_context(silent=True)
    while context is not None:
        if bool(context.params.get("no_interactive")):
            return True
        context = context.parent
    return False


def interactive_available() -> bool:
    """Interaction requires a real stdin TTY and no explicit opt-out."""
    if non_interactive_forced():
        return False
    try:
        return bool(sys.stdin.isatty())
    except (AttributeError, OSError):
        return False


def selected_from_menu() -> bool:
    return os.environ.get(MENU_SELECTION_ENV) == "1"


def child_cli_environment() -> dict[str, str]:
    """Preserve an explicit non-interactive policy across nested CLI launches."""
    env = os.environ.copy()
    if non_interactive_forced():
        env[NON_INTERACTIVE_ENV] = "1"
    return env


def prompt_text(label: str, *, default: str | None = None) -> str:
    try:
        value = Prompt.ask(label, default=default, console=console).strip()
    except (EOFError, KeyboardInterrupt) as exc:
        raise InteractiveInputError("Ввод отменён; действие не выполнено.") from exc
    return value


def prompt_integer(label: str, *, default: int) -> int:
    try:
        return int(IntPrompt.ask(label, default=default, console=console))
    except (EOFError, KeyboardInterrupt) as exc:
        raise InteractiveInputError("Ввод отменён; действие не выполнено.") from exc


def confirm_action(message: str, *, default: bool = False) -> bool:
    """Confirm a menu action without letting EOF or Ctrl-C execute it."""
    try:
        return Confirm.ask(message, default=default, console=console)
    except (EOFError, KeyboardInterrupt) as exc:
        raise InteractiveInputError("Ввод отменён; действие не выполнено.") from exc


def prompt_choice(
    label: str,
    choices: Sequence[tuple[str, str]],
    *,
    default: str | None = None,
) -> str:
    if not choices:
        raise InteractiveInputError("Нет доступных вариантов для выбора.")
    table = Table(title=label)
    table.add_column("№", style="cyan", justify="right")
    table.add_column("Вариант")
    for index, (value, description) in enumerate(choices, start=1):
        table.add_row(str(index), description or value)
    console.print(table)
    labels = [str(index) for index in range(1, len(choices) + 1)]
    try:
        selected = Prompt.ask(
            "Выберите номер",
            choices=labels,
            default=str(choices.index(next(item for item in choices if item[0] == default)) + 1)
            if default is not None and any(item[0] == default for item in choices)
            else None,
            console=console,
        )
    except (EOFError, KeyboardInterrupt) as exc:
        raise InteractiveInputError("Ввод отменён; действие не выполнено.") from exc
    return choices[int(selected) - 1][0]


def prompt_config_path(label: str = "Конфигурация") -> str:
    configs = sorted(Path("configs").glob("*.json")) if Path("configs").is_dir() else []
    choices = [(str(path), str(path)) for path in configs]
    if choices:
        choices.append(("__custom__", "Указать другой путь"))
        selected = prompt_choice(label, choices)
        if selected != "__custom__":
            return selected
    value = prompt_text(f"Путь к {label.lower()}")
    if not value:
        raise InteractiveInputError("Путь не указан; действие не выполнено.")
    return value


def resolve_pipeline_config_for_cli(
    *, site_dir: Path, explicit: str | None, allow_running: bool
) -> str:
    """Use the normal resolver first; ask only when it cannot pick one config."""
    from evileye.stack_control import (
        AmbiguousPipelineConfigError,
        require_pipeline_config,
    )

    try:
        return require_pipeline_config(
            site_dir, explicit=explicit, allow_running=allow_running
        )
    except (AmbiguousPipelineConfigError, FileNotFoundError):
        if explicit is not None or not interactive_available():
            raise
        selected = prompt_config_path("конфигурация pipeline")
        return require_pipeline_config(
            site_dir, explicit=selected, allow_running=allow_running
        )


def _context_prefix(ctx: click.Context) -> list[str]:
    names: list[str] = []
    current: click.Context | None = ctx
    while current is not None and current.parent is not None:
        if current.info_name:
            names.append(current.info_name)
        current = current.parent
    return list(reversed(names))


def _public_commands(ctx: click.Context) -> list[tuple[str, click.Command]]:
    commands = getattr(ctx.command, "commands", {})
    prefix = _context_prefix(ctx)
    return [
        (name, command)
        for name, command in commands.items()
        if not command.hidden
        and (
            GROUP_MENU_POLICIES.get(name, False)
            if isinstance(command, click.Group)
            else COMMAND_POLICIES.get(" ".join([*prefix, name]), CommandInteractionPolicy(menu=False)).menu
        )
    ]


def _requires_menu_confirmation(command_path: Sequence[str]) -> str | None:
    policy = COMMAND_POLICIES.get(" ".join(command_path))
    return policy.confirmation if policy is not None else None


def _menu_arguments(command_path: Sequence[str]) -> list[str] | None:
    """Collect only the inputs that are meaningful for the chosen menu action."""
    path = " ".join(command_path)
    policy = COMMAND_POLICIES.get(path)
    wizard = policy.wizard if policy else None
    if wizard == "run":
        mode = prompt_choice(
            "Что запустить?",
            [("config", "Пайплайн из конфигурации"), ("video", "Обработать видеофайл")],
        )
        value = prompt_text("Путь к конфигурации" if mode == "config" else "Путь к видео")
        if not value:
            raise InteractiveInputError("Путь не указан; запуск отменён.")
        return [value] if mode == "config" else ["--video", value]
    if wizard == "config" and path in {"validate", "prod init"}:
        value = prompt_config_path("конфигурация")
        return [value] if path == "validate" else [value]
    if wizard == "create":
        return [prompt_text("Имя новой конфигурации")]
    if wizard == "plugin-create":
        name = prompt_text("Имя нового плагина")
        template = prompt_choice(
            "Шаблон плагина",
            [
                ("processor", "Обработчик кадров"),
                ("detector", "Детектор объектов"),
                ("alarm", "Детектор тревог"),
                ("source", "Источник видео"),
                ("pipeline", "Класс пайплайна"),
            ],
            default="processor",
        )
        output_dir = prompt_text("Родительский каталог", default=".")
        return [name, "--template", template, "--output-dir", output_dir]
    if wizard == "pipeline-stop":
        target = prompt_pipeline_stop_target()
        if target is None:
            return None
        config, all_runs = target
        return ["--all"] if all_runs else ["--config", str(config)]
    if wizard in {"watchdog-config", "watchdog-check"}:
        selected = prompt_config_path("конфигурация watchdog")
        args = ["--config", selected]
        if wizard == "watchdog-check":
            allow_restart = confirm_action(
                "Разрешить watchdog перезапустить pipeline при необходимости?",
                default=False,
            )
            if not allow_restart:
                args.append("--no-restart")
        return args
    return []


def prompt_pipeline_stop_target() -> tuple[str | None, bool] | None:
    from evileye.stack_control import discover_stack_state

    state = discover_stack_state()
    runs = state.console_runs + state.managed_runs
    configs: list[str] = []
    for record in runs:
        value = str(record.get("config_path") or "").strip()
        if value and value not in configs:
            configs.append(value)
    if not configs:
        console.print("[dim]No active pipeline runs.[/dim]")
        return None
    choices = [(value, value) for value in configs]
    choices.append(("__all__", "Все активные pipeline"))
    selected = prompt_choice("Какой pipeline остановить?", choices)
    if not confirm_action("Подтвердить остановку?", default=False):
        return None
    return (None, True) if selected == "__all__" else (selected, False)


def _dispatch(command_path: Sequence[str]) -> int:
    args = list(command_path)
    additional_args = _menu_arguments(command_path)
    if additional_args is None:
        return 0
    args.extend(additional_args)

    confirmation = _requires_menu_confirmation(command_path)
    if confirmation:
        try:
            confirmed = confirm_action(confirmation, default=False)
        except InteractiveInputError:
            raise
        if not confirmed:
            console.print("[dim]Действие отменено.[/dim]")
            return 0
    env = child_cli_environment()
    env[MENU_SELECTION_ENV] = "1"
    proc = subprocess.run(
        [sys.executable, "-m", "evileye.cli_wrapper", *args],
        cwd=os.getcwd(),
        env=env,
        check=False,
    )
    return int(proc.returncode)


def run_command_menu(ctx: click.Context, *, group_name: str | None = None) -> None:
    """Show the registered public commands and dispatch the selected action."""
    entries = _public_commands(ctx)
    if not entries:
        console.print("[yellow]В этой группе нет доступных команд.[/yellow]")
        raise typer.Exit(2)

    title = "Команды EvilEye" if group_name is None else f"Команды: {group_name}"
    table = Table(title=title)
    table.add_column("№", style="cyan", justify="right")
    table.add_column("Команда", style="green")
    table.add_column("Описание")
    for index, (name, command) in enumerate(entries, start=1):
        description = command.short_help or command.help or ""
        first_line = description.splitlines()[0] if description.splitlines() else ""
        table.add_row(str(index), name, first_line)
    table.add_row("0", "Выход", "")
    console.print(table)

    try:
        selected = Prompt.ask(
            "Выберите команду",
            choices=[str(index) for index in range(0, len(entries) + 1)],
            default="0",
            console=console,
        )
        index = int(selected)
    except (EOFError, KeyboardInterrupt) as exc:
        console.print("[dim]Интерактивный режим завершён.[/dim]")
        raise typer.Exit(0) from exc

    if index == 0:
        raise typer.Exit(0)

    name, command = entries[index - 1]
    command_path = [*_context_prefix(ctx), name]
    if isinstance(command, click.Group):
        # A nested group gets its own menu; retain the selection marker.
        env = os.environ.copy()
        env[MENU_SELECTION_ENV] = "1"
        proc = subprocess.run(
            [sys.executable, "-m", "evileye.cli_wrapper", *command_path],
            cwd=os.getcwd(),
            env=env,
            check=False,
        )
        raise typer.Exit(int(proc.returncode))
    try:
        raise typer.Exit(_dispatch(command_path))
    except InteractiveInputError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(2) from exc


def no_command_fallback(ctx: click.Context) -> None:
    """Keep the current non-TTY no-subcommand behavior (help + exit 2)."""
    console.print(ctx.get_help())
    raise typer.Exit(2)


def handle_group_root(ctx: typer.Context, group_name: str, *, fallback: str | None = None) -> None:
    """Serve group menus on TTY and preserve the old no-command response otherwise."""
    if ctx.invoked_subcommand is not None:
        return
    if not GROUP_MENU_POLICIES.get(group_name, False):
        raise RuntimeError(f"No interactive menu policy registered for group {group_name!r}")
    if interactive_available():
        run_command_menu(ctx, group_name=group_name)
    if fallback:
        console.print(fallback)
        raise typer.Exit(2)
    no_command_fallback(ctx)
