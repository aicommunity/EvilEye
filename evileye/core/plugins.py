"""Plugin discovery and registries for EvilEye extensions.

Third-party distributions expose a zero-argument ``load_plugin`` callable in
the ``evileye.plugins`` entry-point group.  The callable returns a
:class:`PluginSpec`; it is evaluated once during application startup.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
import inspect
import math
import threading
from typing import Any, Callable, Iterable, Mapping, Sequence


PLUGIN_API_VERSION = 1
PLUGIN_ENTRY_POINT_GROUP = "evileye.plugins"
MODULE_KINDS = frozenset(
    {
        "component",
        "source",
        "preprocessor",
        "detector",
        "tracker",
        "attribute",
        "event_detector",
        "alarm_detector",
        "processor_item",
        "batch_processor",
    }
)
EXECUTION_MODES = frozenset({"thread", "process"})
MODULE_RUNTIME_FIELDS = frozenset({
    "type", "module_id", "execution_mode", "source_ids", "queue_size", "ipc_mode",
    "enable", "logger_name", "worker_count", "config",
})


def _validate_json_schema(value: Any, schema: Mapping[str, Any], *, path: str = "") -> None:
    """Validate the JSON-Schema subset used by module and pipeline forms.

    The editor schemas use object/array/scalar types, enums, required keys,
    numeric/string bounds, and ``additionalProperties``. Unknown properties
    are deliberately retained whenever the schema permits them.
    """
    expected = schema.get("type")
    if expected == "any" or expected is None:
        pass
    else:
        expected_types = expected if isinstance(expected, (list, tuple)) else (expected,)
        type_matches = any(_matches_json_type(value, str(type_name)) for type_name in expected_types)
        if not type_matches:
            label = " or ".join(str(item) for item in expected_types)
            raise ValueError(f"{path or 'config'} must be {label}")

    enum = schema.get("enum")
    if isinstance(enum, (list, tuple)) and value not in enum:
        raise ValueError(f"{path or 'config'} must be one of {', '.join(map(str, enum))}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"{path or 'config'} must be finite")
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{path or 'config'} must be >= {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{path or 'config'} must be <= {schema['maximum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise ValueError(f"{path or 'config'} must be > {schema['exclusiveMinimum']}")
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            raise ValueError(f"{path or 'config'} must be < {schema['exclusiveMaximum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise ValueError(f"{path or 'config'} must contain at least {schema['minLength']} characters")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ValueError(f"{path or 'config'} must contain at most {schema['maxLength']} characters")

    if isinstance(value, Mapping):
        properties = schema.get("properties", {})
        properties = properties if isinstance(properties, Mapping) else {}
        for required_key in schema.get("required", ()):
            if required_key not in value:
                raise ValueError(f"{path or 'config'}.{required_key} is required")
        additional = schema.get("additionalProperties", True)
        for key, child in value.items():
            child_schema = properties.get(key)
            child_path = str(key) if not path else (
                f"{path}.{key}" if path.startswith("config.") else f"config.{path}.{key}"
            )
            if child_schema is None:
                if additional is False:
                    raise ValueError(f"{child_path} is not allowed")
                if isinstance(additional, Mapping):
                    _validate_json_schema(child, additional, path=child_path)
                continue
            if isinstance(child_schema, Mapping):
                _validate_json_schema(child, child_schema, path=child_path)
        if not path and expected == "object" and not isinstance(value, Mapping):
            raise ValueError("config must be object")

    if isinstance(value, (list, tuple)):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise ValueError(f"{path or 'config'} must contain at least {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ValueError(f"{path or 'config'} must contain at most {schema['maxItems']} items")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                _validate_json_schema(item, item_schema, path=f"{path or 'config'}[{index}]")


def _matches_json_type(value: Any, type_name: str) -> bool:
    if type_name == "any":
        return True
    if type_name == "null":
        return value is None
    if type_name == "object":
        return isinstance(value, Mapping)
    if type_name == "array":
        return isinstance(value, (list, tuple))
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "string":
        return isinstance(value, str)
    return True


class PluginError(RuntimeError):
    """Raised when a plugin cannot be loaded or violates the public contract."""


@dataclass(frozen=True)
class ModuleRuntimeContext:
    """Serializable runtime metadata passed to worker-local module state."""

    module_id: str
    execution_mode: str
    source_ids: tuple[int, ...] = ()
    worker_count: int = 1


@dataclass(frozen=True)
class ModuleSpec:
    """A module exported by a plugin.

    ``module_id`` is local to the plugin and becomes ``plugin_id/module_id``
    after registration. ``factory`` should be importable at module scope when
    ``process`` execution is advertised. The ``parallel_items`` capability
    means independent ``process_item`` calls may run concurrently with isolated
    state per worker; the runtime restores output order. Modules must not depend
    on shared mutable state between items or workers.
    """

    module_id: str
    kind: str
    factory: Callable[..., Any]
    execution_modes: Sequence[str] = ("thread",)
    capabilities: Sequence[str] = ()
    config_schema: Any = None
    legacy_ids: Sequence[str] = ()
    default_execution_mode: str | None = None
    display_name: str | None = None
    description: str | None = None
    stages: Sequence[str] = ()


@dataclass(frozen=True)
class PipelineSpec:
    """Factory for a custom pipeline implementation."""

    pipeline_id: str
    factory: Callable[..., Any]
    legacy_ids: Sequence[str] = ()
    display_name: str | None = None
    description: str | None = None
    config_schema: Any = None
    topology_provider: Callable[[Mapping[str, Any]], Any] | None = None


@dataclass(frozen=True)
class PluginSpec:
    """Manifest returned from an ``evileye.plugins`` entry point."""

    plugin_id: str
    api_version: int
    modules: Sequence[ModuleSpec] = ()
    pipelines: Sequence[PipelineSpec] = ()


@dataclass(frozen=True)
class RegisteredModule:
    plugin_id: str
    spec: ModuleSpec

    @property
    def qualified_id(self) -> str:
        return f"{self.plugin_id}/{self.spec.module_id}"


@dataclass(frozen=True)
class RegisteredPipeline:
    plugin_id: str
    spec: PipelineSpec

    @property
    def qualified_id(self) -> str:
        return f"{self.plugin_id}/{self.spec.pipeline_id}"


class PluginRegistry:
    """Thread-safe registry shared by builtin and installed plugins."""

    def __init__(self) -> None:
        self._modules: dict[str, RegisteredModule] = {}
        self._module_aliases: dict[str, str] = {}
        self._pipelines: dict[str, RegisteredPipeline] = {}
        self._pipeline_aliases: dict[str, str] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _validate_identifier(value: str, label: str) -> str:
        value = str(value or "").strip()
        if not value or any(ch.isspace() for ch in value):
            raise PluginError(f"Invalid {label}: {value!r}")
        return value

    def register_plugin(self, plugin: PluginSpec) -> None:
        if not isinstance(plugin, PluginSpec):
            raise PluginError("Plugin entry point must return PluginSpec")
        plugin_id = self._validate_identifier(plugin.plugin_id, "plugin_id")
        if plugin.api_version != PLUGIN_API_VERSION:
            raise PluginError(
                f"Plugin '{plugin_id}' uses API {plugin.api_version}; "
                f"EvilEye supports API {PLUGIN_API_VERSION}"
            )

        prepared_modules: list[tuple[str, RegisteredModule, tuple[str, ...]]] = []
        prepared_pipelines: list[tuple[str, RegisteredPipeline, tuple[str, ...]]] = []
        for spec in plugin.modules:
            module_id = self._validate_identifier(spec.module_id, "module_id")
            if "/" in module_id:
                raise PluginError(
                    f"Module id '{module_id}' must be local to plugin '{plugin_id}'"
                )
            if spec.kind not in MODULE_KINDS:
                raise PluginError(
                    f"Plugin '{plugin_id}' module '{module_id}' has unknown kind '{spec.kind}'"
                )
            if not callable(spec.factory):
                raise PluginError(
                    f"Plugin '{plugin_id}' module '{module_id}' factory is not callable"
                )
            modes = set(spec.execution_modes)
            if not modes or not modes.issubset(EXECUTION_MODES):
                raise PluginError(
                    f"Plugin '{plugin_id}' module '{module_id}' has invalid execution modes: "
                    f"{sorted(modes)}"
                )
            if spec.kind == "batch_processor" and "process" in modes:
                raise PluginError(
                    f"Plugin '{plugin_id}' batch processor '{module_id}' only "
                    "supports thread execution in this API version"
                )
            if (
                spec.default_execution_mode is not None
                and spec.default_execution_mode not in modes
            ):
                raise PluginError(
                    f"Plugin '{plugin_id}' module '{module_id}' default execution mode "
                    f"'{spec.default_execution_mode}' is not supported; supported modes: "
                    f"{', '.join(sorted(modes))}"
                )
            if "process" in modes:
                self._validate_spawn_factory(plugin_id, module_id, spec.factory)
            key = f"{plugin_id}/{module_id}"
            aliases = tuple(
                dict.fromkeys(
                    ([module_id] if plugin_id == "evileye" else [])
                    + list(map(str, spec.legacy_ids))
                )
            )
            prepared_modules.append((key, RegisteredModule(plugin_id, spec), aliases))

        for spec in plugin.pipelines:
            pipeline_id = self._validate_identifier(spec.pipeline_id, "pipeline_id")
            if "/" in pipeline_id:
                raise PluginError(
                    f"Pipeline id '{pipeline_id}' must be local to plugin '{plugin_id}'"
                )
            if not callable(spec.factory):
                raise PluginError(
                    f"Plugin '{plugin_id}' pipeline '{pipeline_id}' factory is not callable"
                )
            key = f"{plugin_id}/{pipeline_id}"
            aliases = tuple(
                dict.fromkeys(
                    ([pipeline_id] if plugin_id == "evileye" else [])
                    + list(map(str, spec.legacy_ids))
                )
            )
            prepared_pipelines.append(
                (key, RegisteredPipeline(plugin_id, spec), aliases)
            )

        with self._lock:
            # Validate the whole manifest before mutating the registry.
            module_keys: set[str] = set()
            module_aliases: dict[str, str] = {}
            for key, registered, aliases in prepared_modules:
                if key in module_keys:
                    raise PluginError(f"Duplicate module id in plugin '{plugin_id}': {key}")
                module_keys.add(key)
                previous = self._modules.get(key)
                if previous is not None and previous.spec.factory is not registered.spec.factory:
                    raise PluginError(f"Duplicate module id: {key}")
                for alias in aliases:
                    local_mapped = module_aliases.get(alias)
                    if local_mapped is not None and local_mapped != key:
                        raise PluginError(
                            f"Module alias '{alias}' is declared more than once in plugin '{plugin_id}'"
                        )
                    module_aliases[alias] = key
                    mapped = self._module_aliases.get(alias)
                    if mapped is not None and mapped != key:
                        raise PluginError(
                            f"Module alias '{alias}' is already registered by '{mapped}'"
                        )
                    if alias in self._modules and alias != key:
                        raise PluginError(
                            f"Module alias '{alias}' conflicts with registered module id '{alias}'"
                        )
            pipeline_keys: set[str] = set()
            pipeline_aliases: dict[str, str] = {}
            for key, registered, aliases in prepared_pipelines:
                if key in pipeline_keys:
                    raise PluginError(f"Duplicate pipeline id in plugin '{plugin_id}': {key}")
                pipeline_keys.add(key)
                previous = self._pipelines.get(key)
                if previous is not None and previous.spec.factory is not registered.spec.factory:
                    raise PluginError(f"Duplicate pipeline id: {key}")
                for alias in aliases:
                    local_mapped = pipeline_aliases.get(alias)
                    if local_mapped is not None and local_mapped != key:
                        raise PluginError(
                            f"Pipeline alias '{alias}' is declared more than once in plugin '{plugin_id}'"
                        )
                    pipeline_aliases[alias] = key
                    mapped = self._pipeline_aliases.get(alias)
                    if mapped is not None and mapped != key:
                        raise PluginError(
                            f"Pipeline alias '{alias}' is already registered by '{mapped}'"
                        )
                    if alias in self._pipelines and alias != key:
                        raise PluginError(
                            f"Pipeline alias '{alias}' conflicts with registered pipeline id '{alias}'"
                        )

            for key, registered, aliases in prepared_modules:
                self._modules[key] = registered
                for alias in aliases:
                    self._module_aliases[alias] = key
            for key, registered, aliases in prepared_pipelines:
                self._pipelines[key] = registered
                for alias in aliases:
                    self._pipeline_aliases[alias] = key

    def register_builtin_module(
        self,
        module_id: str,
        factory: Callable[..., Any],
        *,
        kind: str = "component",
        execution_modes: Sequence[str] = ("thread", "process"),
        capabilities: Sequence[str] = (),
        config_schema: Any = None,
        legacy_ids: Sequence[str] = (),
        default_execution_mode: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        stages: Sequence[str] = (),
    ) -> None:
        if display_name is None or description is None or config_schema is None or not stages:
            from evileye.core.builtin_module_schemas import builtin_module_metadata

            builtin_name, builtin_description, builtin_schema, builtin_stages = (
                builtin_module_metadata(module_id)
            )
            display_name = display_name or builtin_name
            description = description or builtin_description
            if config_schema is None:
                config_schema = builtin_schema
            stages = stages or builtin_stages
        spec = ModuleSpec(
            module_id=module_id,
            kind=kind,
            factory=factory,
            execution_modes=execution_modes,
            capabilities=capabilities,
            config_schema=config_schema,
            legacy_ids=tuple(dict.fromkeys([module_id, *legacy_ids])),
            default_execution_mode=default_execution_mode,
            display_name=display_name,
            description=description,
            stages=tuple(stages),
        )
        plugin = PluginSpec("evileye", PLUGIN_API_VERSION, modules=(spec,))
        self.register_plugin(plugin)

    def register_builtin_pipeline(
        self,
        pipeline_id: str,
        factory: Callable[..., Any],
        *,
        legacy_ids: Sequence[str] = (),
        display_name: str | None = None,
        description: str | None = None,
        config_schema: Any = None,
        topology_provider: Callable[[Mapping[str, Any]], Any] | None = None,
    ) -> None:
        if display_name is None or description is None or config_schema is None:
            from evileye.core.builtin_module_schemas import builtin_pipeline_metadata

            builtin_name, builtin_description, builtin_schema, builtin_topology = (
                builtin_pipeline_metadata(pipeline_id)
            )
            display_name = display_name or builtin_name
            description = description or builtin_description
            if config_schema is None:
                config_schema = builtin_schema
            topology_provider = topology_provider or builtin_topology
        spec = PipelineSpec(
            pipeline_id=pipeline_id,
            factory=factory,
            legacy_ids=tuple(dict.fromkeys([pipeline_id, *legacy_ids])),
            display_name=display_name,
            description=description,
            config_schema=config_schema,
            topology_provider=topology_provider,
        )
        self.register_plugin(
            PluginSpec("evileye", PLUGIN_API_VERSION, pipelines=(spec,))
        )

    def get_module(self, module_id: str) -> RegisteredModule | None:
        with self._lock:
            key = module_id if module_id in self._modules else self._module_aliases.get(module_id)
            return self._modules.get(key) if key else None

    def get_pipeline(self, pipeline_id: str) -> RegisteredPipeline | None:
        with self._lock:
            key = (
                pipeline_id
                if pipeline_id in self._pipelines
                else self._pipeline_aliases.get(pipeline_id)
            )
            return self._pipelines.get(key) if key else None

    def list_modules(self, kind: str | None = None) -> list[str]:
        with self._lock:
            return sorted(
                key
                for key, module in self._modules.items()
                if kind is None or module.spec.kind == kind
            )

    def validate_module_config(self, module_id: str, config: Mapping[str, Any]) -> dict[str, Any]:
        """Validate and normalize configuration using the module's declared schema.

        A schema may be a Pydantic model or a callable validator. Callable
        validators may return a normalized mapping, ``True``/``None`` for an
        unchanged valid mapping, or raise an exception with a useful message.
        """
        registered = self.get_module(module_id)
        if registered is None:
            raise PluginError(f"Unknown plugin module '{module_id}'")
        if not isinstance(config, Mapping):
            raise PluginError(
                f"Configuration for module '{registered.qualified_id}' must be an object"
            )
        config_data = dict(config)
        requested_mode = config_data.get("execution_mode")
        if requested_mode is not None and requested_mode not in registered.spec.execution_modes:
            raise PluginError(
                f"Invalid configuration for module '{registered.qualified_id}': "
                "execution_mode must be one of "
                f"{', '.join(registered.spec.execution_modes)}"
            )
        schema = registered.spec.config_schema
        if schema is None:
            return config_data
        try:
            if isinstance(schema, Mapping):
                schema = dict(schema)
                properties = schema.get("properties")
                if isinstance(properties, Mapping) and "execution_mode" in config_data:
                    properties = dict(properties)
                    mode_schema = properties.get("execution_mode")
                    if isinstance(mode_schema, Mapping):
                        mode_schema = dict(mode_schema)
                        mode_schema["enum"] = list(registered.spec.execution_modes)
                        properties["execution_mode"] = mode_schema
                        schema["properties"] = properties
                _validate_json_schema(config_data, schema)
                return config_data
            if callable(getattr(schema, "model_validate", None)):
                validated = schema.model_validate(config_data)
            elif callable(getattr(schema, "parse_obj", None)):
                validated = schema.parse_obj(config_data)
            elif callable(schema):
                validated = schema(config_data)
            else:
                raise TypeError("config_schema must be a Pydantic model or validator callable")
            if validated is None or validated is True:
                return config_data
            if validated is False:
                raise ValueError("validator returned False")
            if callable(getattr(validated, "model_dump", None)):
                validated = validated.model_dump()
            elif callable(getattr(validated, "dict", None)) and not isinstance(validated, Mapping):
                validated = validated.dict()
            if isinstance(validated, Mapping):
                return dict(validated)
            raise TypeError("validator must return a mapping, True, or None")
        except Exception as exc:
            raise PluginError(
                f"Invalid configuration for module '{registered.qualified_id}': {exc}"
            ) from exc

    def validate_pipeline_config(
        self, pipeline_id: str, config: Mapping[str, Any]
    ) -> dict[str, Any]:
        registered = self.get_pipeline(pipeline_id)
        if registered is None:
            raise PluginError(f"Unknown plugin pipeline '{pipeline_id}'")
        if not isinstance(config, Mapping):
            raise PluginError(
                f"Configuration for pipeline '{registered.qualified_id}' must be an object"
            )
        config_data = dict(config)
        schema = registered.spec.config_schema
        if schema is None:
            return config_data
        try:
            if isinstance(schema, Mapping):
                _validate_json_schema(config_data, schema)
                return config_data
            if callable(getattr(schema, "model_validate", None)):
                validated = schema.model_validate(config_data)
            elif callable(getattr(schema, "parse_obj", None)):
                validated = schema.parse_obj(config_data)
            elif callable(schema):
                validated = schema(config_data)
            else:
                raise TypeError("config_schema must be a JSON schema, Pydantic model, or validator")
            if validated is None or validated is True:
                return config_data
            if validated is False:
                raise ValueError("validator returned False")
            if callable(getattr(validated, "model_dump", None)):
                validated = validated.model_dump()
            elif callable(getattr(validated, "dict", None)) and not isinstance(validated, Mapping):
                validated = validated.dict()
            if isinstance(validated, Mapping):
                return dict(validated)
            raise TypeError("validator must return a mapping, True, or None")
        except Exception as exc:
            raise PluginError(
                f"Invalid configuration for pipeline '{registered.qualified_id}': {exc}"
            ) from exc

    def list_pipelines(self) -> list[str]:
        with self._lock:
            return sorted(self._pipelines)

    def list_pipeline_names(self) -> list[str]:
        with self._lock:
            names = set(self._pipeline_aliases)
            names.update(
                key for key, pipeline in self._pipelines.items()
                if pipeline.plugin_id != "evileye"
            )
            return sorted(names)

    def clear(self) -> None:
        """Clear registry state. Intended for tests and isolated app contexts."""
        with self._lock:
            self._modules.clear()
            self._module_aliases.clear()
            self._pipelines.clear()
            self._pipeline_aliases.clear()

    @staticmethod
    def _validate_spawn_factory(plugin_id: str, module_id: str, factory: Callable[..., Any]) -> None:
        if not (inspect.isclass(factory) or inspect.isfunction(factory)):
            raise PluginError(
                f"Plugin '{plugin_id}' module '{module_id}' process factory must be a class or function"
            )
        module_name = getattr(factory, "__module__", None)
        qualname = getattr(factory, "__qualname__", "")
        if not module_name or "<locals>" in qualname or module_name == "__main__":
            raise PluginError(
                f"Plugin '{plugin_id}' module '{module_id}' declares process execution, "
                "but its factory is not importable by multiprocessing spawn"
            )


plugin_registry = PluginRegistry()


class PluginManager:
    """Loads installed Python plugins once, during application startup."""

    def __init__(self, registry: PluginRegistry | None = None) -> None:
        self.registry = registry or plugin_registry
        self._loaded = False
        self._loading = False
        self._lock = threading.RLock()
        self._load_errors: list[str] = []

    @property
    def load_errors(self) -> tuple[str, ...]:
        return tuple(self._load_errors)

    def load(self, entry_points: Iterable[Any] | None = None, *, force: bool = False) -> None:
        with self._lock:
            if self._loaded and not force:
                if self._load_errors:
                    raise PluginError("Plugin loading failed: " + "; ".join(self._load_errors))
                return
            if self._loading:
                return
            self._loading = True
            self._load_errors = []
            try:
                if entry_points is None:
                    entry_points = metadata.entry_points(group=PLUGIN_ENTRY_POINT_GROUP)
                for entry_point in sorted(entry_points, key=lambda ep: (ep.name, ep.value)):
                    try:
                        loaded = entry_point.load()
                        plugin = loaded() if callable(loaded) and not isinstance(loaded, PluginSpec) else loaded
                        self.registry.register_plugin(plugin)
                    except Exception as exc:
                        entry_name = getattr(entry_point, "name", "<unknown>")
                        if isinstance(exc, ModuleNotFoundError):
                            dependency = exc.name or "<unknown>"
                            reason = f"missing dependency '{dependency}': {exc}"
                        else:
                            reason = str(exc)
                        self._load_errors.append(f"{entry_name}: {reason}")
                self._loaded = True
                if self._load_errors:
                    raise PluginError("Plugin loading failed: " + "; ".join(self._load_errors))
            finally:
                self._loading = False


plugin_manager = PluginManager()


def register_module(
    module_id: str,
    *,
    kind: str,
    execution_modes: Sequence[str] = ("thread",),
    capabilities: Sequence[str] = (),
    config_schema: Any = None,
    legacy_ids: Sequence[str] = (),
    default_execution_mode: str | None = None,
    display_name: str | None = None,
    description: str | None = None,
    stages: Sequence[str] = (),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for builtin modules and simple in-process extensions."""

    def decorate(factory: Callable[..., Any]) -> Callable[..., Any]:
        plugin_registry.register_builtin_module(
            module_id,
            factory,
            kind=kind,
            execution_modes=execution_modes,
            capabilities=capabilities,
            config_schema=config_schema,
            legacy_ids=legacy_ids,
            default_execution_mode=default_execution_mode,
            display_name=display_name,
            description=description,
            stages=stages,
        )
        return factory

    return decorate


def register_pipeline(
    pipeline_id: str,
    *,
    display_name: str | None = None,
    description: str | None = None,
    config_schema: Any = None,
    topology_provider: Callable[[Mapping[str, Any]], Any] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for builtin pipeline classes or factories."""

    def decorate(factory: Callable[..., Any]) -> Callable[..., Any]:
        plugin_registry.register_builtin_pipeline(
            pipeline_id,
            factory,
            display_name=display_name,
            description=description,
            config_schema=config_schema,
            topology_provider=topology_provider,
        )
        return factory

    return decorate
