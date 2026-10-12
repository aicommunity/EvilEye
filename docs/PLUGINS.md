# EvilEye plugins

EvilEye loads installed Python plugins when the application starts. It does not
install dependencies or reload code in a running process. For editable development installs, use a pip version with PEP 660 support. In a
fresh or older environment, update pip first with
`python -m pip install --upgrade pip`, then run `python -m pip install -e .`
from the plugin package directory. The package installs into the same Python
environment EvilEye uses.

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
`IStatefulItemProcessor`, `IContextualStatefulItemProcessor`, `ISource`,
`IBatchProcessor`, `IModelClassMappingProvider`, `IEventDetector`, and
`IProcessEventDetector`. Plugins do not inherit from these protocols. The runtime
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
state inside the selected worker. It may accept a second `context` argument of
`ModuleRuntimeContext`, containing the qualified module id, execution mode, and
configured source ids. Existing one-argument and zero-argument state factories
remain valid. Both factory and state are initialized in
the worker, so plugin modules must not depend on parent-process model or device
objects. For `process` mode the factory must be importable at module scope.
Configuration is checked before startup. Inputs are serialized synchronously
before enqueueing, and outputs are serialized in the worker before they reach
the multiprocessing queue; failures become explicit module errors instead of
asynchronous queue feeder errors. State remains inside its worker and does not
cross the process boundary. An optional zero-argument `close()` method on the module or state is called
when its worker stops; legacy lifecycle modules may use `release()` instead.

```python
ModuleSpec(
    module_id="my-detector",
    kind="processor_item",
    factory=MyDetector,
    execution_modes=("thread", "process"),
    default_execution_mode="thread",
)
```

If omitted, the first declared execution mode is the default. Set it explicitly
when changing a built-in module's runtime would otherwise change existing
configuration behavior. The default must be one of `execution_modes`.

For frame processors, declare `capabilities=("accepts_frame_handle",)` when the
module can consume EvilEye's descriptor-backed frame payload without first
materializing its image. Optional metadata such as `"emits_dto_type:Frame"` is
exposed to the pipeline's compatibility diagnostics. Without the handle
capability the pipeline materializes a frame before calling the module.

In process mode, the item runtime places Frame.image in shared memory and sends
a lightweight Frame containing frame metadata and frame_handle/frame_ref. The
module must read that descriptor (for example with
SharedFrameTransport.get_frame_view); it must not assume Frame.image is set.
When the module returns the same Frame as part of its result, the runtime
reconnects it to the original parent-side Frame and releases the shared-memory
segment. In thread mode the module receives the ordinary materialized Frame.


A model-backed processor that publishes class IDs implements
`get_model_class_mapping() -> Mapping[str, int]` and declares
`capabilities=("model_class_mapping",)`. The runtime validates the mapping and
publishes it from the worker to the controller in both execution modes. In
process mode the worker sends metadata independently of frame results, including
when the model loads lazily. The controller merges the mapping into
`ClassManager` and the visualizer. The provider method and capability must be
present together; changing a published mapping while the worker runs marks the
module degraded.

The runtime owns bounded queues and worker lifecycle. If an input queue fills,
a `Frame` (or `(data, Frame)` pair) replaces the oldest pending frame;
`input_queue_dropped` increments and the module becomes degraded. Other payloads
are rejected with an explicit error and `input_queue_rejected` counter. Ordered
parallel modules mark an evicted frame sequence as skipped so later outputs are
not blocked. Worker output queues apply backpressure and do not silently discard
results.

## Sources

A source plugin uses `kind="source"` and implements `open()`, `read()`, and
`close()`. `read()` returns the next EvilEye frame/item or `None` at end of
stream. It may advertise `thread`, `process`, or both. Process mode recreates
the source in a spawn child from its importable factory and config.

For `PipelineSurveillance`, each source item must be an `evileye.core.frame.Frame`:

- `source_id` is the configured logical source ID. `frame_id` is a per-source
  sequence ID and must be preserved across detector/tracker stages. If the
  source resets that sequence on reconnect or rewind, it must increment
  `connection_generation`; built-in capture starts at generation zero. The GStreamer file loop advances it at EOS before emitting frames from the next loop.
- `image` is the HxWx3 BGR NumPy image used by both built-in capture backends.
  Treat emitted image data as immutable. `time_stamp` is acquisition wall time
  in seconds; `pts_ns` and `media_pts_sec` are optional source media-clock data.
  Video-file index, position (milliseconds), and duration fields are optional.
- Runtime transport may attach a `frame_handle` for shared-memory delivery.
  Modules that declare `accepts_frame_handle` must read it through
  `SharedFrameTransport`; the runtime owns descriptor release. Ordinary source
  plugins return a materialized `image` and do not manage shared memory.

`CaptureImage` is a compatibility alias for `Frame`. General-purpose source SPI
implementations may return other item types, but the surveillance pipeline's
source stage expects `Frame` values.

## Detector outputs in PipelineSurveillance

A detector item should return a pair `(detection_batch, frame)`. For a detector
that must feed the built-in tracker, use the public lazy exports
`DetectionResult` and `DetectionResultList`:

```python
from evileye.object_detector import DetectionResult, DetectionResultList

def process_item(self, item, state):
    frame = item[-1] if isinstance(item, (tuple, list)) else item
    batch = DetectionResultList()
    batch.source_id = frame.source_id
    batch.frame_id = frame.frame_id
    batch.time_stamp = frame.time_stamp

    detection = DetectionResult()
    detection.bounding_box = [x1, y1, x2, y2]  # source-frame pixel coordinates
    detection.confidence = 0.93
    detection.class_id = 0
    batch.detections.append(detection)
    return batch, frame
```

Each detection carries `bounding_box` in XYXY source-frame coordinates,
`confidence`, and integer `class_id`; optional plugin metadata can be stored
in `detection_data`. A mapping result is also accepted by the built-in tracker
when it contains `source_id`, `frame_id`, and a `detections` list with those
fields. Keep the batch metadata aligned with the frame.

When several detectors are assigned to the same source, the pipeline joins
their `detections` lists by `(source_id, connection_generation, frame_id)`
and sends one combined item to the next stage. Return the original frame with
its identity unchanged. A mismatched or missing frame identity cannot be joined
and is reported as incomplete fanout. Process-mode outputs, including detection
objects and custom `detection_data`, must be pickle-serializable.

The pipeline setting `detector_fanout_policy` controls an incomplete join:

- `forward_partial` (default) forwards results that arrived and marks the
  pipeline degraded, preserving existing configurations.
- `drop_frame` discards that detector-stage output instead of sending a partial
  result downstream. Runtime health reports the incomplete and dropped counts.

Use `drop_frame` when a downstream rule must only evaluate a complete detector
ensemble. A dropped frame is not an assertion that no violation occurred; the
pipeline is degraded and that health state must be handled by the application.
Unknown policy values fail pipeline initialization.

Fanout bounds can be tuned per surveillance pipeline with positive
`detector_fanout_timeout_sec` and integer `detector_fanout_max_pending` settings.
The defaults are 30 seconds and 512 pending frames. The legacy
`EVILEYE_DETECTOR_FANOUT_TIMEOUT_SEC` environment setting supplies the timeout
default when the pipeline config omits it. Effective values are included in
detector-stage runtime health.

`DetectionResultList` can pass directly into the built-in BoT-SORT module. If
the detector publishes class names, implement
`get_model_class_mapping() -> Mapping[str, int]` and declare the
`model_class_mapping` capability so the controller and visualizer receive the
same class IDs.

## Built-in migration

`PreprocessingPipeline` and `RoiFeeder` are now registered as item processors
and use the same runtime as external `processor_item` modules. Their legacy
`type` configs remain valid. `RoiFeeder` accepts both `thread` and `process`;
choose `process` when the isolation benefit is worth serializing each frame and
tracking result.

`VideoCaptureOpencv` and `VideoCaptureGStreamer` are registered through the
source SPI and created by `SourceModuleAdapter`. The adapter exposes a common
source to `PipelineSurveillance`, while delegating capture metadata,
subscriptions, and lifecycle to the capture implementation. A source configured
with `execution_mode="process"` still uses its specialized `MpWorkerCapture`
backend; the adapter polls it from a host thread and reports both the adapter
mode and backend mode. Runtime diagnostics include parent-observed availability
transitions, the backend connection generation carried by frames, and worker
metrics. The capture worker acknowledges shared-memory frame descriptors before
releasing them, so short finite videos are delivered before the worker exits.
External source plugins implement the simpler `open/read/close` contract and do
not need to subclass `EvilEyeBase`. `open()` runs once before the read loop and
`close()` runs in the worker's cleanup path. A `read()` call returns one new
item or `None` at EOF; repeatedly returning the same latest `Frame` is not a
valid source sequence. For `Frame`, source/frame IDs and connection generation
identify a unique item. In thread mode, `read()` must return within a bounded
interval so the runtime can observe shutdown; the SPI has no cross-thread
cancellation method. A thread that exceeds the stop timeout remains
visible as running/degraded, and the adapter rejects reconfiguration or restart
until it exits. Use process mode for blocking native or network reads: the host
can terminate a child that does not stop before its timeout, and reports that
forced termination as degraded.

Built-in YOLO, RT-DETR, RF-DETR, BoT-SORT, and attribute detector/classifier
modules are registered as `processor_item` modules and execute through
`ItemModuleAdapter`. Model and tracker state is created inside the selected
thread or spawn worker. The adapter owns queueing, lifecycle, shutdown, and
worker diagnostics; plugin classes implement the module contract instead of a
second pipeline-facing put/get runtime.

PipelineSurveillance starts frame workers before sources and waits for each
worker's initialization handshake before it starts capture. Item modules must
finish required model/runtime initialization in their factory or create_state;
the readiness signal is not a promise that a lazily initialized first
process_item call has completed. Startup fails and cleans up if a worker fails
or does not become ready within EVILEYE_FRAME_WORKER_READY_TIMEOUT_SEC
(default: 30 seconds). Sources are not started against an unready detector.
When finite sources reach EOF with autoclose, the controller drains queued
and in-flight stage work before shutdown. The drain is bounded by
EVILEYE_AUTOCLOSE_DRAIN_TIMEOUT_SEC (default: 60 seconds); a timeout is
reported with the modules that still have pending work. Bounded item queues
may still discard stale frames under overload, and those drops are reported
in runtime diagnostics. Synchronous custom pipelines can use the base
pipeline's empty backlog; a pipeline with asynchronous stages must implement
has_pending_work() and get_pending_work_summary() so autoclose does not stop
before its own workers finish. Existing config names remain valid, including
`ObjectDetectorYoloMp` as an alias for `ObjectDetectorYolo`.
`LegacyProcessorModuleAdapter` remains a compatibility bridge for modules that
still expose only the old `put/get` contract; the migrated built-ins do not use
it.

`AttributeDetector` and `AttributeClassifier` resolve configured
`attrs` against checkpoint class names when `class_mapping` is
omitted or empty. If a requested label is missing, the module fails with a
configuration error and requires an explicit mapping instead of treating the
order of `attrs` as model class IDs.

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

Legacy event modules declare `kind="event_detector"` and retain their
thread lifecycle. A module that reads live `ObjectsHandler` or capture source
objects uses the `object_handler` or `capture_sources` capability and stays
in thread mode.

A process event module declares
`execution_modes=("process",)` and one or more input capabilities:
`event_updates` for object snapshots, `source_updates` for camera state
transitions, or `event_commands` for explicit controller commands. The
`event_frames` capability extends `event_updates` with bounded JPEG
attachments. Its top-level factory accepts a config mapping and returns an
object implementing
`process_update(update: EventUpdate, state)`. The optional
`create_state(config, context)` runs inside the spawned worker. Optional
`start()` and `stop()` methods also run in that worker. The factory must be
importable at module scope.

For `event_updates`, the host subscribes the module to `ObjectsHandler` and
transfers one `EventUpdate(kind="object_snapshot")` per configured source after
each object update. For `source_updates`, it subscribes to capture sources and
sends serialized disconnect/reconnect transitions as
`EventUpdate(kind="source_status")`. Capture sources notify subscribers when
they record a connection transition. The object snapshot `payload` contains
primitive `active` and `lost` object summaries with ids, class id, timestamp,
`time_detected`/`time_lost`, bounding box, attributes, and history summaries.
With `event_frames`, each object can reference a JPEG attachment by index; a
frame is limited to 2 MiB, an update to 4 MiB and 16 attachments, and the input
queue to four frame-bearing updates. Exceeding a limit marks the detector
degraded instead of silently dropping evidence. Live model objects, handlers,
and locks do not cross the process boundary. Plugins can
also accept explicit `EventUpdate` values through `put()`. Process modules
cannot declare `object_handler` or `capture_sources`; the runtime rejects those
live dependencies before start. Modules using `event_commands` receive explicit
updates through `put()`. Controller lifecycle messages that arrive before
worker startup are buffered in a bounded queue and flushed after the child
reports ready.
The builtin `SystemEventsDetector` uses `event_commands`; the builtin
`CamEventsDetector` uses `source_updates`; and
`ScheduleAlarmEventsDetector` uses `event_updates`; `AttributeEventsDetector`
uses `event_updates` and `event_frames` to preserve evidence images.
`ZoneEventsDetector` uses `event_updates`, `event_frames`, and
`event_commands`; the `zone_commands` capability connects UI edits to the
worker. It retains the existing geometry, dwell/exit thresholds, return-to-zone
handling, and enter/exit evidence. The schedule detector uses timestamp and
class metadata from object history to preserve its existing start/finish
behavior; it does not need frame pixels. The adapter preserves the
controller-facing `emit_message`, `emit_started`, and `emit_stopped` calls.
Modules that declare `event_commands` can receive named commands through
`EventDetectorModuleAdapter.submit_command()`; command names and payloads must
be validated by that module. During normal shutdown, accepted worker updates are processed and their output
is retained for the final event-controller flush. Managed runs signal the
pipeline owner first, allowing it to stop modules and drain accepted work;
remaining process-group members are force-killed only after the configured
grace period.

```python
from evileye.core.contracts import EventUpdate
from evileye.core.plugins import ModuleSpec, PluginSpec, PLUGIN_API_VERSION
from evileye.events_detectors.alarm_event import AlarmEvent

class SafetyRule:
    def __init__(self, config):
        self.required_attributes = set(config["required_attributes"])

    def process_update(self, update: EventUpdate, state):
        alarms = []
        for obj in update.payload["active"]:
            present = {
                name for name, value in obj["attributes"].items()
                if value.get("state") == "exists"
            }
            missing = self.required_attributes - present
            if missing:
                alarms.append(AlarmEvent(
                    "ppe_violation",
                    severity="critical",
                    source_id=update.source_id,
                    details={"object_id": obj["object_id"], "missing": sorted(missing)},
                ))
        return alarms

def load_plugin():
    return PluginSpec(
        plugin_id="site_safety",
        api_version=PLUGIN_API_VERSION,
        modules=(ModuleSpec(
            module_id="ppe_rule",
            kind="event_detector",
            factory=SafetyRule,
            execution_modes=("process",),
            capabilities=("event_updates",),
        ),),
    )
```

`process_update` returns `None`, one event, or a list/tuple of events. Event
objects must be pickle-serializable. For a generic custom alarm, return
`AlarmEvent(alarm_type, severity=..., source_id=..., details=...)`; it is
persisted by the generic JSON and PostgreSQL adapters and displayed by the
events journal. A stable `alarm_id` makes retries idempotent. Both the host update queue and
worker input queue are bounded; overflow rejects the update and sets a degraded
runtime diagnostic. Failure to start an enabled event detector aborts event
startup and stops detectors already started in that pass. This reports loss
but does not promise delivery of an alarm that existed only in memory when the
host process crashed.

## Custom pipelines

A plugin can include `PipelineSpec`. Its factory receives
`PipelineDependencies`, whose `config.raw_config` and `config.credentials`
contain the requested runtime configuration. The returned object must satisfy
the existing `IPipeline` contract. Builtin pipeline class names remain
available; an unknown or invalid requested pipeline now fails startup rather
than falling back to `PipelineSurveillance`.
