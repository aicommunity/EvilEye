# EvilEye plugins

EvilEye loads installed Python plugins when the application starts. It does not
install dependencies or reload code in a running process. During development,
install a plugin package into the EvilEye environment with `pip install -e .`.

## Declare a plugin package

Add an entry point to the plugin's `pyproject.toml`:

```toml
[project.entry-points."evileye.plugins"]
my_plugin = "my_plugin:load_plugin"
```

The callable returns a `PluginSpec` with a stable `plugin_id`, the
`PLUGIN_API_VERSION`, and module or pipeline declarations. The public types are
available from `evileye.core.plugins`. Module ids are namespaced at runtime as
`plugin_id/module_id`; use `legacy_ids` only when preserving an existing config
name. A duplicate id or legacy alias, incompatible API version, import error,
or invalid execution capability stops plugin loading with a diagnostic.
`ModuleSpec.config_schema` accepts a Pydantic model or validator callable. A
callable can return a normalized mapping, return `True`/`None` when the input is
valid, or raise an exception with a validation message.

See [`examples/plugin_package`](../examples/plugin_package) for a minimal
installable package.

## Runtime contracts

The structural protocols are in `evileye.core.interfaces`: `IItemProcessor`,
`IStatefulItemProcessor`, `ISource`, `IBatchProcessor`, and
`IEventDetector`. Plugins do not inherit from these protocols. The runtime
validates the required callable methods when the module is initialized.

The common item, source, and batch adapters expose `get_runtime_stats()`
through `IRuntimeStatusProvider`. The status includes the qualified module id, selected
execution mode, and degraded state; asynchronous adapters add worker and queue
details. A synchronous batch processor reports whether its module instance is
initialized because it has no background worker. Initialization and processing
exceptions are logged, set the adapter to degraded, and are surfaced to the
pipeline caller where the stage contract allows it.

## Item processors

An item processor is a factory that returns an object implementing
`process_item(item, state)`. The optional `create_state(config)` method creates
state inside the selected worker. Both factory and state are initialized in
the worker, so plugin modules must not depend on parent-process model or device
objects. For `process` mode the factory must be importable at module scope and
the configuration, inputs, outputs, and state must be spawn/pickle compatible.
An optional zero-argument `close()` method on the module or state is called
when its worker stops; legacy lifecycle modules may use `release()` instead.

```python
ModuleSpec(
    module_id="my-detector",
    kind="processor_item",
    factory=MyDetector,
    execution_modes=("thread", "process"),
)
```

For frame processors, declare `capabilities=("accepts_frame_handle",)` when the
module can consume EvilEye's descriptor-backed frame payload without first
materializing its image. Optional metadata such as `"emits_dto_type:Frame"` is
exposed to the pipeline's compatibility diagnostics. Without the handle
capability the pipeline materializes a frame before calling the module.

The runtime owns the bounded queues and worker lifecycle. A full input queue or
worker failure marks the module degraded and is logged; the runtime does not
silently discard a queued result.

## Sources

A source plugin uses `kind="source"` and implements `open()`, `read()`, and
`close()`. `read()` returns the next EvilEye frame/item or `None` at end of
stream. It may advertise `thread`, `process`, or both. Process mode recreates
the source in a spawn child from its importable factory and config.

## Built-in migration

`PreprocessingPipeline` and `RoiFeeder` are now registered as item processors
and use the same runtime as external `processor_item` modules. Their legacy
`type` configs remain valid. `RoiFeeder` accepts both `thread` and `process`;
choose `process` when the isolation benefit is worth serializing each frame and
tracking result.

`VideoCaptureOpencv` and `VideoCaptureGStreamer` are registered through the
source SPI and created by `SourceModuleAdapter`. The adapter exposes a common
source to `PipelineSurveillance`, while delegating capture metadata,
subscriptions, and lifecycle to the existing capture implementation. This
keeps recording and multi-camera behavior intact. A source configured with
`execution_mode="process"` still uses the capture module's existing
`MpWorkerCapture` backend; the adapter itself polls that backend in a host
thread and reports both `execution_mode` and `backend_execution_mode` in its
runtime diagnostics. The capture worker acknowledges shared-memory frame
descriptors before releasing them, so short finite videos are delivered before
the worker exits. External source plugins should implement the simpler
`open/read/close` contract described above and do not need to subclass
`EvilEyeBase`.

Built-in YOLO/RT-DETR detectors, BoT-SORT, and attribute detector/classifier
modules are also registered in the SPI. `LegacyProcessorModuleAdapter` bridges
their established `put/get` and lifecycle contracts into the pipeline module
boundary; their proven model and process-worker internals remain unchanged.
`ObjectDetectorYoloMp` is a compatibility config alias for `ObjectDetectorYolo`; the configured `execution_mode` selects the canonical detector runtime.

New plugins should implement `process_item(item, state)` and use the common
runtime directly. For stages that consume a synchronized multi-source batch,
declare `kind="batch_processor"` and implement
`process_batch(batch, state)`. `ObjectMultiCameraTracking` uses this contract
via `BatchProcessorModuleAdapter`; it coordinates results across cameras and
currently advertises thread execution only. The runtime rejects a requested
process mode before starting a thread-only module.

## Configure `PipelineSurveillance`

Use `module_id` to select a namespaced plugin. The old per-item `type` value
continues to work for builtin and legacy modules.

```json
{
  "pipeline_class": "PipelineSurveillance",
  "detectors": [{"type": "ObjectDetectorYolo", "source_ids": [0]}],
  "modules": {
    "detectors": {
      "mode": "extend",
      "items": [{"module_id": "my_plugin/my-detector", "source_ids": [0], "execution_mode": "process"}]
    }
  }
}
```

Supported groups are `sources`, `preprocessors`, `detectors`, `trackers`,
`mc_trackers`, `attributes_roi`, and `attributes_classifier`. `extend` appends
the listed items to the corresponding legacy section; `replace` uses only the
listed items. `ProcessorStep` sends a frame to every matching detector or
tracker instead of stopping at the first matching `source_id`.

## Event detectors and alarms

An event module declares `kind="event_detector"` (and
`capabilities=("object_handler",)` when it subscribes to ObjectsHandler). It
must follow EvilEye's event-detector lifecycle and emit event objects. For a
generic custom alarm, use `AlarmEvent(alarm_type, severity=..., source_id=...,
details=...)`; it is persisted by the generic JSON and PostgreSQL adapters and
displayed by the events journal. A stable `alarm_id` makes retries idempotent.
Queues and persistence errors are reported in runtime diagnostics. The first
release does not promise delivery of an alarm that existed only in memory when
the host process crashed.

## Custom pipelines

A plugin can include `PipelineSpec`. Its factory receives
`PipelineDependencies`, whose `config.raw_config` and `config.credentials`
contain the requested runtime configuration. The returned object must satisfy
the existing `IPipeline` contract. Builtin pipeline class names remain
available; an unknown or invalid requested pipeline now fails startup rather
than falling back to `PipelineSurveillance`.
