"""Plugin discovery and registries for EvilEye extensions.

Third-party distributions expose a zero-argument ``load_plugin`` callable in
the ``evileye.plugins`` entry-point group.  The callable returns a
:class:`PluginSpec`; it is evaluated once during application startup.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
import inspect
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


class PluginError(RuntimeError):
    """Raised when a plugin cannot be loaded or violates the public contract."""


@dataclass(frozen=True)
class ModuleRuntimeContext:
    """Serializable runtime metadata passed to worker-local module state."""

    module_id: str
    execution_mode: str
    source_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class ModuleSpec:
    """A module exported by a plugin.

    ``module_id`` is local to the plugin and becomes ``plugin_id/module_id``
    after registration. ``factory`` should be importable at module scope when
    ``process`` execution is advertised.
    """

    module_id: str
    kind: str
    factory: Callable[..., Any]
    execution_modes: Sequence[str] = ("thread",)
    capabilities: Sequence[str] = ()
    config_schema: Any = None
    legacy_ids: Sequence[str] = ()


@dataclass(frozen=True)
class PipelineSpec:
    """Factory for a custom pipeline implementation."""

    pipeline_id: str
    factory: Callable[..., Any]
    legacy_ids: Sequence[str] = ()


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
    ) -> None:
        spec = ModuleSpec(
            module_id=module_id,
            kind=kind,
            factory=factory,
            execution_modes=execution_modes,
            capabilities=capabilities,
            config_schema=config_schema,
            legacy_ids=tuple(dict.fromkeys([module_id, *legacy_ids])),
        )
        plugin = PluginSpec("evileye", PLUGIN_API_VERSION, modules=(spec,))
        self.register_plugin(plugin)

    def register_builtin_pipeline(
        self,
        pipeline_id: str,
        factory: Callable[..., Any],
        *,
        legacy_ids: Sequence[str] = (),
    ) -> None:
        spec = PipelineSpec(
            pipeline_id=pipeline_id,
            factory=factory,
            legacy_ids=tuple(dict.fromkeys([pipeline_id, *legacy_ids])),
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
        schema = registered.spec.config_schema
        if schema is None:
            return config_data
        try:
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
                        self._load_errors.append(
                            f"{getattr(entry_point, 'name', '<unknown>')}: {exc}"
                        )
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
        )
        return factory

    return decorate


def register_pipeline(
    pipeline_id: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for builtin pipeline classes or factories."""

    def decorate(factory: Callable[..., Any]) -> Callable[..., Any]:
        plugin_registry.register_builtin_pipeline(pipeline_id, factory)
        return factory

    return decorate
