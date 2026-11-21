"""SSH-friendly pipeline configuration wizard."""

from __future__ import annotations

import copy
import difflib
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

import typer
from rich.prompt import Confirm, Prompt
from rich.table import Table

from evileye.cli_commands.console import console
from evileye.core.pipeline_configuration import (
    BACKUP_LIMIT,
    SURVEILLANCE_GROUPS,
    builtin_pipeline_kind as _builtin_pipeline_kind,
    group_storage as _group_storage,
    known_module_id as _known_module_id,
    pipeline_and_root as _pipeline_and_root,
    schema_mapping as _schema_mapping,
    validate_configuration,
    write_config_with_backup as _write_config_with_backup,
)

def _uri_has_userinfo(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        return bool(parsed.scheme and parsed.netloc and "@" in parsed.netloc)
    except ValueError:
        return False


def _redact_uri_userinfo(value: Any) -> Any:
    if not _uri_has_userinfo(value):
        return value
    parsed = urlsplit(value)
    authority = parsed.netloc.rsplit("@", 1)[-1]
    return urlunsplit(parsed._replace(netloc=f"***:***@{authority}"))


def _safe_form_value(key: str, value: Any, schema: Mapping[str, Any]) -> str:
    if schema.get("secret") or schema.get("writeOnly") or any(term in key.lower() for term in ("password", "secret", "token", "api_key", "private_key")):
        return "••••••"
    if _uri_has_userinfo(value):
        value = _redact_uri_userinfo(value)
    return json.dumps(value, ensure_ascii=False)

def _prompt_field(name: str, schema: Mapping[str, Any], current: Any = None,
                  *, present: bool = False) -> tuple[bool, Any]:
    from evileye.cli_interactive import prompt_choice
    from evileye.core.plugins import _validate_json_schema

    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        choices = [(str(value), str(value)) for value in enum]
        selected = prompt_choice(f"{name}: {schema.get('description', '')}".strip(), choices,
                                 default=str(current) if present else None)
        return True, next(value for value in enum if str(value) == selected)
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((item for item in kind if item != "null"), "string")
    if kind == "boolean":
        default = bool(current) if present else bool(schema.get("default", False))
        try:
            return True, Confirm.ask(name, default=default, console=console)
        except (EOFError, KeyboardInterrupt) as exc:
            from evileye.cli_interactive import InteractiveInputError
            raise InteractiveInputError("Настройка отменена; конфиг не сохранён.") from exc

    default = current if present else schema.get("default")
    if kind in {"array", "object"} or kind is None:
        default_text = json.dumps(default, ensure_ascii=False) if default is not None else ""
    else:
        default_text = "" if default is None else str(default)
    label = f"{name} ({schema.get('description')})" if schema.get("description") else name
    secret = (
        bool(schema.get("secret"))
        or bool(schema.get("writeOnly"))
        or any(term in name.lower() for term in ("password", "secret", "token", "api_key", "private_key"))
        or _uri_has_userinfo(current)
    )
    if secret:
        # Rich echoes defaults even when password input is enabled.
        default_text = ""
    while True:
        try:
            value = Prompt.ask(label, default=default_text, console=console, password=secret).strip()
        except (EOFError, KeyboardInterrupt) as exc:
            from evileye.cli_interactive import InteractiveInputError
            raise InteractiveInputError("Настройка отменена; конфиг не сохранён.") from exc
        if secret and value == "<empty>":
            return True, ""
        if secret and not value:
            return (True, current) if present else (False, None)
        if kind in {"array", "object"} or kind is None:
            if not value and not present and "default" not in schema:
                return False, None
            try:
                parsed = None if value == "<null>" else json.loads(value) if value else default
                _validate_json_schema(parsed, schema, path=name)
                return True, parsed
            except (json.JSONDecodeError, ValueError) as exc:
                console.print(f"[yellow]Некорректное значение: {exc}. Введите JSON.[/yellow]")
                continue
        if not value and not present and "default" not in schema:
            return False, None
        if not value and present and current is None and "null" in (schema.get("type") if isinstance(schema.get("type"), list) else []):
            return True, None
        if value == "<null>" and "null" in (schema.get("type") if isinstance(schema.get("type"), list) else []):
            return True, None
        try:
            if kind == "integer":
                parsed = int(value)
            elif kind == "number":
                parsed = float(value)
            elif kind == "boolean":
                parsed = value.lower() in {"1", "true", "yes", "on"}
            else:
                parsed = value
            _validate_json_schema(parsed, schema, path=name)
            return True, parsed
        except ValueError as exc:
            console.print(f"[yellow]Некорректное значение: {exc}.[/yellow]")


def edit_module_form(module_id: str, item: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Edit known fields interactively; retain all unrecognized legacy fields."""
    from evileye.core.plugins import plugin_registry, MODULE_RUNTIME_FIELDS

    registered = plugin_registry.get_module(module_id)
    if registered is None:
        raise ValueError(f"Модуль не зарегистрирован: {module_id}")
    schema = _schema_mapping(registered.spec.config_schema)
    if not schema:
        raise ValueError(f"У модуля {registered.qualified_id} нет схемы формы")
    props = schema.get("properties", {})
    props.setdefault("execution_mode", {"type": "string"})
    if registered.spec.kind in {"processor_item", "source", "batch_processor"}:
        props.setdefault("source_ids", {"type": "array", "items": {"type": "integer"}})
    execution_mode_schema = props.get("execution_mode")
    if isinstance(execution_mode_schema, dict):
        execution_mode_schema["enum"] = list(registered.spec.execution_modes)
    edited = copy.deepcopy(dict(item or {}))
    payload = edited.get("config") if isinstance(edited.get("config"), dict) else edited
    edited.setdefault("module_id", registered.qualified_id)
    if "execution_mode" in props and "execution_mode" not in edited:
        default_mode = registered.spec.default_execution_mode or tuple(registered.spec.execution_modes)[0]
        edited["execution_mode"] = default_mode

    while True:
        table = Table(title=registered.spec.display_name or registered.qualified_id)
        table.add_column("Поле")
        table.add_column("Текущее значение")
        editable: list[str] = []
        for key, field_schema in props.items():
            if key in {"type", "module_id"}:
                continue
            editable.append(key)
            values = edited if key in MODULE_RUNTIME_FIELDS else payload
            if key in values:
                value = _safe_form_value(key, values[key], field_schema)
            elif "default" in field_schema:
                value = f"(по умолчанию: {field_schema['default']})"
            else:
                value = "(не задано)"
            table.add_row(key, value)
        unknown = sorted(key for key in payload if key not in props and key not in MODULE_RUNTIME_FIELDS)
        if unknown:
            table.add_row("прочие поля", ", ".join(unknown))
        console.print(table)
        choices = [(key, key) for key in editable]
        choices.append(("__unknown__", "Прочие поля: добавить или изменить JSON-поле"))
        choices.append(("__done__", "Готово"))
        selected = _choose("Поле для настройки", choices, default="__done__")
        if selected == "__done__":
            return edited
        if selected == "__unknown__":
            key = _ask_text("Имя JSON-поля")
            if not key or key in {"module_id"}:
                continue
            value_text = _ask_text("JSON-значение")
            try:
                (edited if key in MODULE_RUNTIME_FIELDS else payload)[key] = json.loads(value_text)
            except json.JSONDecodeError as exc:
                console.print(f"[yellow]Некорректный JSON: {exc}[/yellow]")
            continue
        schema_field = props[selected]
        values = edited if selected in MODULE_RUNTIME_FIELDS else payload
        present, value = _prompt_field(selected, schema_field, values.get(selected), present=selected in values)
        if present:
            values[selected] = value
        else:
            values.pop(selected, None)


def _ask_text(label: str, default: str | None = None) -> str:
    try:
        return Prompt.ask(label, default=default, console=console).strip()
    except (EOFError, KeyboardInterrupt) as exc:
        from evileye.cli_interactive import InteractiveInputError
        raise InteractiveInputError("Настройка отменена; конфиг не сохранён.") from exc


def _confirm(label: str, *, default: bool) -> bool:
    try:
        return Confirm.ask(label, default=default, console=console)
    except (EOFError, KeyboardInterrupt) as exc:
        from evileye.cli_interactive import InteractiveInputError
        raise InteractiveInputError("Настройка отменена; конфиг не сохранён.") from exc


def _choose(label: str, choices: list[tuple[str, str]], *, default: str | None = None) -> str:
    from evileye.cli_interactive import prompt_choice
    return prompt_choice(label, choices, default=default)


def _set_group_storage(pipeline: dict[str, Any], group: str, items: list[Any], base_count: int,
                       mode: str | None) -> None:
    if mode is None:
        pipeline[group] = items
    elif mode == "replace":
        pipeline.setdefault("modules", {}).setdefault(group, {})["items"] = items
    else:
        split = max(0, min(int(base_count), len(items)))
        pipeline[group] = items[:split]
        pipeline.setdefault("modules", {}).setdefault(group, {})["items"] = items[split:]


def _event_items(root: dict[str, Any]) -> tuple[list[tuple[str, Any]], str]:
    from evileye.events_detectors.event_registry import DEFAULT_ENABLED_EVENT_DETECTORS

    values = root.get("events_detectors")
    if not isinstance(values, dict):
        values = {}
    items = [(key, value) for key, value in values.items() if key != "enabled"]
    configured = {key for key, _value in items}
    enabled = values.get("enabled")
    active = enabled if isinstance(enabled, list) else DEFAULT_ENABLED_EVENT_DETECTORS
    items.extend((str(name), {}) for name in active if str(name) not in configured)
    return items, "events"


def _available_modules(kind: str, stage: str | None = None) -> list[tuple[str, str]]:
    from evileye.core.plugins import plugin_registry

    choices = []
    for qualified in plugin_registry.list_modules(kind):
        registered = plugin_registry.get_module(qualified)
        if not registered or not _schema_mapping(registered.spec.config_schema):
            continue
        declared_stages = set(registered.spec.stages or ())
        if stage and declared_stages:
            compatible_stages = {stage}
            compatible_stages.update({
                "source": {"sources"},
                "frame": {"preprocessors"},
                "step": {
                    "detectors", "trackers", "mc_trackers",
                    "attributes_roi", "attributes_classifier",
                },
            }.get(stage, set()))
            if not declared_stages.intersection(compatible_stages):
                continue
        name = registered.spec.display_name or qualified
        modes = ", ".join(registered.spec.execution_modes)
        choices.append((qualified, f"{name} · {qualified} · {modes}"))
    return choices


def _edit_list(group: str, title: str, kind: str, fallback: str | None,
               get_items, set_items, *, stage_filter: str | None = None,
               is_enabled=None, toggle_enabled=None, allow_move: bool = True,
               allowed_module_ids: set[str] | None = None, max_items: int | None = None) -> None:
    from evileye.core.plugins import plugin_registry
    from evileye.cli_interactive import InteractiveInputError

    while True:
        entries = get_items()
        console.print(f"\n[bold]{title}[/bold]")
        if entries:
            table = Table()
            table.add_column("№", justify="right")
            table.add_column("Модуль")
            table.add_column("Имя")
            if is_enabled is not None:
                table.add_column("Статус")
            for index, (identity, item) in enumerate(entries):
                module_id = _known_module_id(item, fallback or identity)
                registered = plugin_registry.get_module(module_id)
                display = registered.spec.display_name if registered else module_id
                label = item.get("name", "") if isinstance(item, Mapping) else ""
                row = [str(index + 1), str(display), str(label)]
                if is_enabled is not None:
                    row.append("включён" if is_enabled(identity, item) else "выключен")
                table.add_row(*row)
            console.print(table)
        actions = [("add", "Добавить модуль")]
        if entries:
            actions.extend([
                ("edit", "Настроить модуль"),
                ("remove", "Удалить модуль"),
            ])
            if toggle_enabled is not None:
                actions.append(("toggle", "Включить или выключить модуль"))
            if allow_move:
                actions.append(("move", "Изменить порядок"))
        actions.append(("back", "Назад"))
        action = _choose("Действие", actions, default="back")
        if action == "back":
            return
        if action == "add":
            if max_items is not None and len(entries) >= max_items:
                console.print(f"[yellow]Эта стадия поддерживает не более {max_items} модулей.[/yellow]")
                continue
            choices = _available_modules(kind, stage_filter or group)
            if allowed_module_ids is not None:
                choices = [(identity, label) for identity, label in choices if identity in allowed_module_ids]
            if not choices:
                console.print(f"[yellow]Для стадии нет модулей со схемой формы (kind={kind}).[/yellow]")
                continue
            module_id = _choose("Выберите модуль", choices)
            try:
                value = edit_module_form(module_id)
            except InteractiveInputError:
                raise
            except Exception as exc:
                console.print(f"[yellow]Не удалось настроить модуль: {exc}[/yellow]")
                continue
            entries.append((module_id, value))
            set_items(entries)
        elif action == "edit":
            index = _pick_index(entries, "Модуль для настройки")
            if index is None:
                continue
            old_identity, old_item = entries[index]
            module_id = _known_module_id(old_item, fallback or old_identity)
            try:
                entries[index] = (old_identity, edit_module_form(module_id, old_item))
                set_items(entries)
            except InteractiveInputError:
                raise
            except Exception as exc:
                console.print(f"[yellow]{exc}[/yellow]")
        elif action == "remove":
            index = _pick_index(entries, "Модуль для удаления")
            if index is not None and _confirm("Удалить выбранный модуль?", default=False):
                entries.pop(index)
                set_items(entries)
        elif action == "move":
            index = _pick_index(entries, "Модуль для перемещения")
            if index is None:
                continue
            target = _pick_index(entries, "Новое место для модуля")
            if target is not None:
                moved = entries.pop(index)
                entries.insert(target, moved)
                set_items(entries)
        elif action == "toggle" and toggle_enabled is not None:
            index = _pick_index(entries, "Модуль для переключения")
            if index is not None:
                identity, item = entries[index]
                toggle_enabled(identity, item)


def _pick_index(items: list[Any], label: str) -> int | None:
    choices = [(str(index), f"{index + 1}. {_known_module_id(item[1], item[0])}") for index, item in enumerate(items)]
    if not choices:
        return None
    return int(_choose(label, choices))


def _configure_declarative(pipeline: dict[str, Any]) -> None:
    from evileye.core.pipeline_topology import declarative_stage_configs

    if "stages" in pipeline and not isinstance(pipeline["stages"], list):
        raise ValueError("pipeline.stages must be an array")
    initial = copy.deepcopy(declarative_stage_configs(pipeline))
    stages = copy.deepcopy(initial)
    while True:
        choices = [(str(i), f"{stage.get('name', f'stage_{i}')} ({stage.get('kind', 'step')})")
                   for i, stage in enumerate(stages) if isinstance(stage, dict)]
        choices.append(("__add__", "Создать стадию"))
        choices.append(("__back__", "Завершить настройку стадий"))
        selected = _choose("Стадия PipelineDeclarative", choices, default="__back__")
        if selected == "__back__":
            if stages != initial:
                pipeline["stages"] = stages
            return
        if selected == "__add__":
            name = _ask_text("Имя стадии")
            if not name:
                continue
            if any(isinstance(stage, Mapping) and str(stage.get("name") or f"stage_{index}") == name
                   for index, stage in enumerate(stages)):
                console.print("[yellow]Имя стадии уже используется.[/yellow]")
                continue
            kind = _choose("Тип стадии", [("source", "Источник"), ("frame", "Обработка кадра"), ("step", "Обычный шаг")])
            stages.append({"name": name, "kind": kind, "items": []})
            selected = str(len(stages) - 1)
        stage_index = int(selected)
        stage = stages[stage_index]
        kind = str(stage.get("kind") or "step")
        allowed = {"source": "source", "frame": "processor_item", "step": "processor_item"}.get(kind, "processor_item")
        items = stage.setdefault("items", [])
        def get_items():
            return [(str(i), item) for i, item in enumerate(items)]
        def set_items(entries):
            items[:] = [item for _, item in entries]
        _edit_list(f"stage:{stage_index}", str(stage.get("name") or f"stage_{stage_index}"), allowed,
                   {"source": "VideoCaptureOpencv", "frame": "PreprocessingPipeline", "step": "ObjectDetectorYolo"}.get(kind),
                   get_items, set_items, stage_filter=kind)


def _configure_events(root: dict[str, Any]) -> None:
    from evileye.events_detectors.event_registry import DEFAULT_ENABLED_EVENT_DETECTORS

    def get_items():
        return _event_items(root)[0]

    def set_items(entries):
        current = root.get("events_detectors")
        current = current if isinstance(current, dict) else {}
        previous_names = {key for key in current if key != "enabled"}
        old_enabled = current.get("enabled")
        previously_active = old_enabled if isinstance(old_enabled, list) else DEFAULT_ENABLED_EVENT_DETECTORS
        previous_names.update(str(name) for name in previously_active)
        next_items = {key: value for key, value in entries}
        next_names = set(next_items)
        removed = previous_names - next_names
        added = next_names - previous_names
        if removed or added:
            active = list(previously_active)
            active = [str(name) for name in active if str(name) not in removed]
            for key, _value in entries:
                if key in added and key not in active:
                    active.append(key)
            next_items["enabled"] = active
        elif isinstance(old_enabled, list):
            next_items["enabled"] = list(old_enabled)
        root["events_detectors"] = next_items

    def is_enabled(identity, _item):
        config = root.get("events_detectors")
        enabled = config.get("enabled") if isinstance(config, dict) else None
        return identity in (enabled if isinstance(enabled, list) else DEFAULT_ENABLED_EVENT_DETECTORS)

    def toggle_enabled(identity, _item):
        config = root.setdefault("events_detectors", {})
        if not isinstance(config, dict):
            config = {}
            root["events_detectors"] = config
        enabled = config.get("enabled")
        active = list(enabled) if isinstance(enabled, list) else list(DEFAULT_ENABLED_EVENT_DETECTORS)
        if identity in active:
            active = [name for name in active if name != identity]
        else:
            active.append(identity)
        config["enabled"] = active

    title, kind, fallback = SURVEILLANCE_GROUPS["events_detectors"]
    _edit_list("events_detectors", title, kind, fallback, get_items, set_items,
               stage_filter="events_detectors", is_enabled=is_enabled,
               toggle_enabled=toggle_enabled, allow_move=False)


def _pipeline_form_fields(pipeline_id: str, excluded_fields: set[str] | None = None) -> dict[str, Any]:
    from evileye.core.plugins import plugin_registry

    registered = plugin_registry.get_pipeline(pipeline_id)
    if registered is None:
        return {}
    schema = _schema_mapping(registered.spec.config_schema)
    if not schema:
        return {}
    excluded = {"pipeline_class", *(excluded_fields or set())}
    return {
        key: value for key, value in schema.get("properties", {}).items()
        if key not in excluded
    }


def _edit_pipeline_config_form(
    pipeline: dict[str, Any], pipeline_id: str, *, excluded_fields: set[str] | None = None,
) -> None:
    from evileye.core.plugins import plugin_registry

    registered = plugin_registry.get_pipeline(pipeline_id)
    if registered is None:
        console.print(f"[yellow]Пайплайн {pipeline_id} не зарегистрирован; его параметры можно сохранить только вручную.[/yellow]")
        return
    if not _schema_mapping(registered.spec.config_schema):
        console.print("[yellow]Плагин не объявил схему формы pipeline; внутренние параметры настраиваются вручную.[/yellow]")
        return
    fields = _pipeline_form_fields(pipeline_id, excluded_fields)
    if not fields:
        return
    if _builtin_pipeline_kind(pipeline_id) == "PipelineDeclarative" and "final_results" in fields:
        from evileye.core.pipeline_topology import declarative_stage_configs

        names = [str(stage.get("name") or f"stage_{index}")
                 for index, stage in enumerate(declarative_stage_configs(pipeline))
                 if isinstance(stage, Mapping) and stage.get("items")]
        if names:
            fields["final_results"] = {**fields["final_results"], "enum": names}
    while True:
        choices = [(key, key) for key in fields]
        choices.append(("__done__", "Готово"))
        selected = _choose(f"Параметры {registered.spec.display_name or pipeline_id}", choices, default="__done__")
        if selected == "__done__":
            return
        present, value = _prompt_field(selected, fields[selected], pipeline.get(selected), present=selected in pipeline)
        if present:
            pipeline[selected] = value
        else:
            pipeline.pop(selected, None)


def _redact_diff(old: Any, new: Any, key: str = "", *, secret_keys: set[str] | None = None) -> tuple[Any, Any]:
    sensitive = key in (secret_keys or set()) or any(token in key.lower() for token in ("password", "secret", "token", "username", "credential", "api_key", "private_key"))
    if sensitive:
        if old == new:
            return "<redacted>", "<redacted>"
        return ("<redacted: previous>", "<redacted: proposed>")
    if isinstance(old, dict) or isinstance(new, dict):
        old_map = old if isinstance(old, dict) else {}
        new_map = new if isinstance(new, dict) else {}
        old_result, new_result = {}, {}
        for child_key in dict.fromkeys([*old_map.keys(), *new_map.keys()]):
            before, after = _redact_diff(old_map.get(child_key), new_map.get(child_key), str(child_key), secret_keys=secret_keys)
            if child_key in old_map:
                old_result[child_key] = before
            if child_key in new_map:
                new_result[child_key] = after
        return old_result, new_result
    if isinstance(old, list) or isinstance(new, list):
        old_list = old if isinstance(old, list) else []
        new_list = new if isinstance(new, list) else []
        before, after = [], []
        for index in range(max(len(old_list), len(new_list))):
            left = old_list[index] if index < len(old_list) else None
            right = new_list[index] if index < len(new_list) else None
            redacted_left, redacted_right = _redact_diff(left, right, key, secret_keys=secret_keys)
            if index < len(old_list):
                before.append(redacted_left)
            if index < len(new_list):
                after.append(redacted_right)
        return before, after
    if _uri_has_userinfo(old) or _uri_has_userinfo(new):
        before, after = _redact_uri_userinfo(old), _redact_uri_userinfo(new)
        if old != new and before == after:
            return f"{before} <previous credentials>", f"{after} <proposed credentials>"
        return before, after
    return old, new


def _diff(old: dict[str, Any] | None, new: dict[str, Any]) -> str:
    from evileye.core.plugins import plugin_registry

    secret_keys: set[str] = set()
    def collect(schema):
        if not isinstance(schema, Mapping):
            return
        properties = schema.get("properties")
        if isinstance(properties, Mapping):
            for key, field in properties.items():
                if isinstance(field, Mapping) and (field.get("secret") or field.get("writeOnly")):
                    secret_keys.add(str(key))
        for value in schema.values():
            if isinstance(value, Mapping):
                collect(value)
            elif isinstance(value, list):
                for item in value:
                    collect(item)
    for identity in plugin_registry.list_modules():
        collect(_schema_mapping(plugin_registry.get_module(identity).spec.config_schema))
    for identity in plugin_registry.list_pipelines():
        collect(_schema_mapping(plugin_registry.get_pipeline(identity).spec.config_schema))
    safe_old, safe_new = _redact_diff(old or {}, new, secret_keys=secret_keys)
    old_text = json.dumps(safe_old, ensure_ascii=False, indent=2).splitlines()
    new_text = json.dumps(safe_new, ensure_ascii=False, indent=2).splitlines()
    return "\n".join(difflib.unified_diff(old_text, new_text, fromfile="current", tofile="proposed", lineterm=""))


def configure_pipeline(config: str | None = typer.Argument(None, help="Config path to create or edit.")) -> None:
    """Interactively configure registered modules and save with a backup."""
    from evileye.cli_interactive import interactive_available, InteractiveInputError
    from evileye.core.builtin_inventory import register_builtins
    from evileye.core.plugins import plugin_registry

    if not interactive_available():
        console.print("[red]Pipeline configuration requires an interactive TTY. Use pipeline inspect or edit JSON manually without a TTY.[/red]")
        raise typer.Exit(2)
    try:
        register_builtins()
        if not config:
            from evileye.cli_interactive import prompt_config_path
            config = prompt_config_path("конфигурация pipeline")
        from evileye.utils.config_paths import normalize_config_path
        path = Path(normalize_config_path(config)).expanduser().resolve()
        original: dict[str, Any] | None = None
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("Config root must be a JSON object")
            original = loaded
            proposed = copy.deepcopy(loaded)
        else:
            class_names = [(name, registered.spec.display_name or name)
                           for name in plugin_registry.list_pipeline_names()
                           if (registered := plugin_registry.get_pipeline(name))]
            selected = _choose("Тип нового pipeline", class_names, default="PipelineSurveillance")
            proposed = {"pipeline": {"pipeline_class": selected}, "events_detectors": {}}
            original = None
        pipeline, root = _pipeline_and_root(proposed)
        pipeline_id = str(pipeline.get("pipeline_class") or "PipelineSurveillance")
        builtin_kind = _builtin_pipeline_kind(pipeline_id)
        if builtin_kind == "PipelineDeclarative":
            _configure_declarative(pipeline)
            _edit_pipeline_config_form(pipeline, pipeline_id, excluded_fields={"stages"})
        elif builtin_kind == "PipelineSurveillance":
            active_groups = dict(SURVEILLANCE_GROUPS)
            active_groups.pop("events_detectors", None)
            while True:
                groups = [(key, f"{label} ({len(_group_storage(pipeline, key)[0])})")
                          for key, (label, _kind, _fallback) in active_groups.items()]
                groups.append(("__done__", "Проверить и завершить"))
                group = _choose("Стадия pipeline", groups, default="__done__")
                if group == "__done__":
                    break
                title, kind, fallback = active_groups[group]
                items, base_count, mode = _group_storage(pipeline, group)
                def get_items(items=items):
                    return [(str(i), value) for i, value in enumerate(items)]
                def set_items(entries, group=group, items=items, base_count=base_count, mode=mode):
                    items[:] = [value for _, value in entries]
                    _set_group_storage(pipeline, group, items, base_count, mode)
                _edit_list(group, title, kind, fallback, get_items, set_items)
            _edit_pipeline_config_form(
                pipeline, pipeline_id,
                excluded_fields={"sources", "preprocessors", "detectors", "trackers", "mc_trackers",
                                 "attributes_roi", "attributes_classifier", "modules"},
            )
        elif builtin_kind == "PipelineCapture":
            items, base_count, mode = _group_storage(pipeline, "sources")
            def get_capture_items():
                return [(str(i), value) for i, value in enumerate(items)]
            def set_capture_items(entries):
                items[:] = [value for _, value in entries]
                _set_group_storage(pipeline, "sources", items, base_count, mode)
            _edit_list("sources", "Источники", "source", "VideoCaptureOpencv", get_capture_items, set_capture_items,
                       stage_filter="sources", allowed_module_ids={"evileye/VideoCaptureOpencv"}, max_items=1)
            _edit_pipeline_config_form(pipeline, pipeline_id, excluded_fields={"sources"})
        else:
            _edit_pipeline_config_form(pipeline, pipeline_id)

        _configure_events(root)

        diagnostics = validate_configuration(proposed)
        if diagnostics:
            console.print("[yellow]Проверка конфигурации:[/yellow]")
            for diagnostic in diagnostics:
                console.print(f"  • {diagnostic}")
            if any("(preserved for manual configuration)" not in issue for issue in diagnostics):
                console.print("[red]Исправьте ошибки конфигурации; сохранение отменено.[/red]")
                raise typer.Exit(1)
        if json.dumps(proposed, sort_keys=True) == json.dumps(original or {}, sort_keys=True):
            console.print("[dim]Изменений нет; файл не перезаписан.[/dim]")
            return
        diff = _diff(original, proposed)
        console.print("[bold]Изменения конфигурации[/bold]")
        console.print(diff or "[dim]Нет изменений[/dim]", markup=False)
        if not _confirm(f"Сохранить в {path}? Будет создана резервная копия; хранятся последние {BACKUP_LIMIT}.", default=False):
            console.print("[yellow]Сохранение отменено.[/yellow]")
            return
        content = json.dumps(proposed, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        backup = _write_config_with_backup(path, content)
        if backup:
            console.print(f"[green]Сохранено:[/green] {path}\n[dim]Резервная копия: {backup}[/dim]")
        else:
            console.print(f"[green]Сохранено:[/green] {path}")
    except InteractiveInputError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(2) from exc
    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Pipeline configuration failed: {exc}[/red]")
        raise typer.Exit(1) from exc
