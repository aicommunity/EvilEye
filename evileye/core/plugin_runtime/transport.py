"""Serialization, frame transport and factory helpers shared by the runtime adapters."""

from __future__ import annotations

import inspect
import pickle
import time
from typing import Any, Mapping

from ..plugins import ModuleRuntimeContext, PluginError

_PROCESS_INPUT_MARKER = "__evileye_plugin_input__"


_PROCESS_OUTPUT_MARKER = "__evileye_plugin_runtime__"


class _IncomingFrameDropped:
    def __init__(self, evicted_payload=None):
        self.evicted_payload = evicted_payload


def _is_frame_work_item(item: Any) -> bool:
    """Frame work can shed stale queued frames; other payloads reject overflow."""
    from ..frame import Frame

    if isinstance(item, Frame):
        return True
    return (
        isinstance(item, (tuple, list))
        and len(item) == 2
        and isinstance(item[1], Frame)
    )


def _serialize_process_value(value: Any, module_id: str, label: str) -> bytes:
    try:
        return pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as exc:
        raise PluginError(
            f"Module '{module_id}' {label} must be serializable for process "
            f"execution: {exc}"
        ) from exc


_PROCESS_RESULT_MARKER = "__evileye_plugin_result__"


_FRAME_RUNTIME_KEY = "_evileye_runtime_frame_key"


_FRAME_METADATA_FIELDS = (
    "source_id", "frame_id", "frame_version", "connection_generation", "current_video_frame",
    "current_video_position", "source_video_duration", "time_stamp", "pts_ns",
    "media_pts_sec",
)


def _prepare_item_for_process(item: Any, transport, request_id: int):
    from ..frame import Frame

    frames: dict[int, Frame] = {}
    handles = []

    def convert(value):
        if isinstance(value, Frame):
            frame_index = len(frames)
            frames[frame_index] = value
            handle = getattr(value, "frame_handle", None)
            if handle is None:
                handle = getattr(value, "frame_ref", None)
            image = getattr(value, "image", None)
            if image is not None:
                handle = transport.alloc_frame(
                    image=image,
                    frame_id=int(getattr(value, "frame_id", 0) or 0),
                    timestamp=float(getattr(value, "time_stamp", None) or time.time()),
                )
                handles.append(handle)

            descriptor = Frame()
            for field in _FRAME_METADATA_FIELDS:
                setattr(descriptor, field, getattr(value, field, None))
            descriptor.image = None
            descriptor.subscribers = []
            descriptor.frame_handle = handle
            descriptor.frame_ref = handle
            setattr(descriptor, _FRAME_RUNTIME_KEY, (request_id, frame_index))
            return descriptor
        if isinstance(value, tuple):
            return tuple(convert(part) for part in value)
        if isinstance(value, list):
            return [convert(part) for part in value]
        if isinstance(value, dict):
            return {key: convert(part) for key, part in value.items()}
        return value

    try:
        return convert(item), frames, handles
    except Exception:
        for handle in handles:
            transport.release_frame(handle)
        raise


def _restore_process_result(value: Any, frames: dict[int, Any], request_id: int):
    from ..frame import Frame

    if isinstance(value, Frame):
        key = getattr(value, _FRAME_RUNTIME_KEY, None)
        if not (
            isinstance(key, tuple) and len(key) == 2
            and key[0] == request_id and isinstance(key[1], int)
        ):
            return value
        original = frames.get(key[1])
        if original is None:
            return value
        for field in _FRAME_METADATA_FIELDS:
            setattr(original, field, getattr(value, field, None))
        return original
    if isinstance(value, tuple):
        return tuple(_restore_process_result(part, frames, request_id) for part in value)
    if isinstance(value, list):
        return [_restore_process_result(part, frames, request_id) for part in value]
    if isinstance(value, dict):
        return {
            key: _restore_process_result(part, frames, request_id)
            for key, part in value.items()
        }
    return value


def _request_id_from_process_payload(payload: Any) -> int | None:
    if (
        isinstance(payload, tuple) and len(payload) == 3
        and payload[0] == _PROCESS_INPUT_MARKER and isinstance(payload[1], int)
    ):
        return payload[1]
    return None


def _call_factory(factory, config: dict[str, Any]):
    """Call a plugin factory with its config when its signature accepts it."""
    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError):
        return factory(config)
    positional = [
        p for p in signature.parameters.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    if positional:
        return factory(config)
    if "config" in signature.parameters:
        return factory(config=config)
    return factory()


def _create_state(
    module: Any,
    config: dict[str, Any],
    context: ModuleRuntimeContext | None = None,
) -> Any:
    create_state = getattr(module, "create_state", None)
    if not callable(create_state):
        return None
    try:
        signature = inspect.signature(create_state)
    except (TypeError, ValueError):
        return create_state(config)
    parameters = signature.parameters
    positional = [
        p for p in parameters.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    if len(positional) >= 2:
        return create_state(config, context)
    if "context" in parameters:
        if positional:
            return create_state(config, context=context)
        kwargs = {"context": context}
        if "config" in parameters:
            kwargs["config"] = config
        return create_state(**kwargs)
    if positional:
        return create_state(config)
    if "config" in parameters:
        return create_state(config=config)
    return create_state()


def _normalize_model_class_mapping(mapping: Any, module_id: str) -> dict[str, int] | None:
    if mapping is None:
        return None
    if not isinstance(mapping, Mapping):
        raise PluginError(
            f"Module '{module_id}' class mapping metadata must be a mapping"
        )
    normalized: dict[str, int] = {}
    for name, class_id in mapping.items():
        if not isinstance(name, str) or not name.strip():
            raise PluginError(
                f"Module '{module_id}' class mapping keys must be non-empty strings"
            )
        if not isinstance(class_id, int) or isinstance(class_id, bool) or class_id < 0:
            raise PluginError(
                f"Module '{module_id}' class mapping values must be non-negative integers"
            )
        normalized[name] = class_id
    return normalized


def _get_model_class_mapping(module: Any, module_id: str) -> dict[str, int] | None:
    provider = getattr(module, "get_model_class_mapping", None)
    if not callable(provider):
        return None
    mapping = provider()
    if mapping is None:
        return None
    try:
        return _normalize_model_class_mapping(mapping, module_id)
    except PluginError as exc:
        raise PluginError(
            f"Module '{module_id}' get_model_class_mapping() is invalid: {exc}"
        ) from exc


def _validate_model_class_mapping_capability(
    module: Any, module_id: str, declared: bool
) -> None:
    provider_exists = callable(getattr(module, "get_model_class_mapping", None))
    if declared and not provider_exists:
        raise PluginError(
            f"Module '{module_id}' declares model_class_mapping but does not "
            "implement get_model_class_mapping()"
        )
    if provider_exists and not declared:
        raise PluginError(
            f"Module '{module_id}' implements get_model_class_mapping() but "
            "does not declare the model_class_mapping capability"
        )


def _close_item_resources(module: Any, state: Any, logger, module_id: str) -> None:
    """Close optional per-worker module/state resources without double-closing."""
    seen: set[int] = set()
    for target in (state, module):
        if target is None or id(target) in seen:
            continue
        seen.add(id(target))
        close = getattr(target, "close", None)
        if not callable(close):
            close = getattr(target, "release", None)
        if not callable(close):
            continue
        try:
            close()
        except Exception:
            if logger:
                logger.exception("Plugin module %s failed to close worker resources", module_id)
