"""Configuration form schemas for the modules shipped with EvilEye.

The schemas intentionally allow additional properties. Configurations have
evolved over time and the CLI editor must preserve fields it does not know.
"""

from __future__ import annotations

from typing import Any


def _field(kind: str, description: str = "", **options: Any) -> dict[str, Any]:
    value: dict[str, Any] = {"type": kind}
    if description:
        value["description"] = description
    value.update(options)
    return value


def _array(item_type: str = "any", description: str = "", **options: Any) -> dict[str, Any]:
    value = _field("array", description, items={"type": item_type}, **options)
    return value


def _nullable(field: dict[str, Any]) -> dict[str, Any]:
    value = dict(field)
    kind = value.get("type")
    value["type"] = list(kind) + ["null"] if isinstance(kind, list) else [kind, "null"]
    return value


COMMON = {
    "type": _field("string", "Legacy module identifier."),
    "module_id": _field("string", "Qualified plugin module identifier."),
    "enable": _field("boolean", "Whether the configured module is enabled.", default=True),
    "enabled": _field("boolean", "Whether the configured module is enabled.", default=True),
    "source_ids": _array("integer", "Logical camera source IDs."),
    "execution_mode": _field("string", "Worker mode.", enum=["thread", "process"]),
    "queue_size": _field("integer", "Runtime queue capacity.", minimum=1),
    "worker_count": _field("integer", "Independent item workers (where supported).", minimum=1),
    "ipc_mode": _field("string", "Frame transport mode.", enum=["standard", "descriptor"]),
    "mp_restart_on_exit": _field("boolean", "Restart a failed process worker.", default=True),
    "mp_no_restart_exit_codes": _array("integer", "Exit codes that should not restart a worker."),
}

_SOURCE = {
    **COMMON,
    "source": _field("string", "Source protocol, such as VideoFile or IpCamera."),
    "camera": _field(["string", "integer"], "File path, camera index, or stream URL."),
    "path": _field("string", "Legacy path to a video file or source."),
    "source_names": _array("string", "Display names for configured cameras."),
    "desired_fps": _nullable(_field("number", "Requested capture rate; null uses source rate.")),
    "source_fps": _nullable(_field("number", "Legacy requested source rate; null uses the source rate.")),
    "fps": _nullable(_field("number", "Legacy requested source rate; null uses the source rate.")),
    "apiPreference": _field("string", "OpenCV capture backend.", enum=["CAP_ANY", "CAP_FFMPEG", "CAP_GSTREAMER", "CAP_IMAGES"]),
    "loop_play": _field("boolean", "Loop file sources at end of stream."),
    "split": _field("boolean", "Split a source into multiple logical streams."),
    "num_split": _nullable(_field("integer", "Number of split streams.", minimum=0)),
    "src_coords": _nullable(_array("any", "Source coordinate/crop configuration.")),
    "capture": _field("object", "Capture queue and reconnect settings.", properties={
        "queue_size": _field("integer", minimum=1),
        "min_sleep_seconds": _field("number", minimum=0),
        "default_sleep_seconds": _field("number", minimum=0),
        "frame_timeout_seconds": _field("number", minimum=0),
        "reconnect_monitor_interval": _field("number", minimum=0),
        "init_grace_period_seconds": _field("number", minimum=0),
        "default_fps_fallback": _field("number", minimum=0),
        "ignore_udp_stream_errors": _field("boolean"),
    }, additionalProperties=True),
    "record": _nullable(_field("object", "Recording configuration.", properties={
        "enabled": _field("boolean", default=False),
        "enabled_sources": _array("string", "Source names enabled for recording."),
        "container": _field("string", default="mp4"),
        "segment_length_sec": _field("integer", minimum=1),
        "retention_days": _field("integer", minimum=0),
        "min_free_space_pct": _field("integer", minimum=0, maximum=100),
        "min_file_size_kb": _field("integer", minimum=0),
        "out_dir": _field("string"),
        "filename_tmpl": _field("string"),
        "continuous_recording_enabled": _field("boolean"),
        "event_recording_enabled": _field("boolean"),
        "event_pre_seconds": _field("integer", minimum=0),
        "event_post_seconds": _field("integer", minimum=0),
        "event_buffer_fps": _nullable(_field("number", minimum=0)),
        "validate_video_integrity": _field("boolean"),
        "video_validation_timeout": _field("number", minimum=0),
    }, additionalProperties=True)),
    "username": _nullable(_field("string", "Source username.", secret=True)),
    "password": _nullable(_field("string", "Source password.", secret=True)),
    "gstreamer_available": _field("boolean", "GStreamer availability override."),
}

_DETECTOR = {
    **COMMON,
    "model": _field("string", "Model name or path."),
    "classes": _array("any", "Class names or numeric class IDs."),
    "conf": _field("number", "Confidence threshold.", minimum=0, maximum=1),
    "conf_thresh": _field("number", "Legacy confidence threshold.", minimum=0, maximum=1),
    "conf_threshold": _field("number", "Legacy confidence threshold.", minimum=0, maximum=1),
    "inference_size": _field("integer", "Inference image size.", minimum=1),
    "imgsz": _field("integer", "Legacy inference image size.", minimum=1),
    "device": _nullable(_field("string", "Inference device, for example cpu or 0; null selects automatically.")),
    "roi": _nullable(_array("any", "Per-source regions of interest.")),
    "vid_stride": _field("integer", "Process every Nth frame.", minimum=1, default=1),
    "stride_type": _field("string", "Frame stride interpretation."),
    "num_detection_threads": _field("integer", "Parallel workers for this detector.", minimum=1, default=1),
    "half": _field("boolean", "Enable half precision when supported."),
    "show": _field("boolean", "Show inference preview."),
    "save": _field("boolean", "Save inference output."),
    "model_class_mapping": _field("object", "Model class name to integer ID mapping.", additionalProperties={"type": "integer"}),
}

_TRACKER = {
    **COMMON,
    "fps": _field("integer", "Expected input frame rate.", minimum=1),
    "track_thresh": _field("number", "Legacy tracker detection threshold.", minimum=0, maximum=1),
    "match_thresh": _field("number", "Legacy tracker matching threshold.", minimum=0, maximum=1),
    "num_tracking_threads": _field("integer", "Legacy tracker worker count.", minimum=1),
    "tracker_onnx": _field("string", "Optional ReID encoder model path."),
    "botsort_cfg": _field("object", "BoT-SORT settings.", properties={
        "tracker_type": _field("string", default="botsort"),
        "track_high_thresh": _field("number", minimum=0, maximum=1),
        "track_low_thresh": _field("number", minimum=0, maximum=1),
        "new_track_thresh": _field("number", minimum=0, maximum=1),
        "track_buffer": _field("integer", minimum=1),
        "match_thresh": _field("number", minimum=0, maximum=1),
        "proximity_thresh": _field("number", minimum=0, maximum=1),
        "appearance_thresh": _field("number", minimum=0, maximum=1),
        "gmc_method": _field("string"),
        "fuse_score": _field("boolean"),
        "with_reid": _field("boolean"),
    }, additionalProperties=True),
}

_ATTRIBUTE = {
    **COMMON,
    "model": _field("string", "Model name or path."),
    "attrs": _array("string", "Attribute names to detect or classify."),
    "class_mapping": _field("object", "Attribute name to model class ID mapping.", additionalProperties={"type": "integer"}),
    "confidence_thresholds": _field("object", "Per-attribute confidence thresholds.", additionalProperties={"type": "number"}),
    "model_class_mapping": _field("object", "Model class name to integer ID mapping.", additionalProperties={"type": "integer"}),
    "conf_threshold": _field("number", "Classification confidence threshold.", minimum=0, maximum=1),
    "conf": _field("number", "Detection confidence threshold.", minimum=0, maximum=1),
    "inference_size": _field("integer", "Inference image size.", minimum=1),
    "device": _nullable(_field("string", "Inference device.")),
    "roi": _nullable(_array("any", "Per-source regions of interest.")),
    "vid_stride": _field("integer", "Process every Nth frame.", minimum=1),
    "num_detection_threads": _field("integer", "Worker count.", minimum=1),
    "show": _field("boolean", "Show inference preview."),
    "save": _field("boolean", "Save inference output."),
}

_EVENT = {
    **COMMON,
    "enabled": _field("boolean", "Whether the event detector is enabled.", default=True),
    "sources": _field("object", "Per-source event rules.", additionalProperties=True),
    "event_threshold": _field("number", "Event threshold."),
    "zone_left_threshold": _field("number", "Zone-left event threshold."),
    "camera_cooldown_sec": _field("integer", "Minimum delay between camera alarms.", minimum=0),
    "default_schedule": _field("object", "Default alarm schedule.", properties={
        "enabled": _field("boolean"),
        "weekdays": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 6}},
        "periods": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
        "class_ids": _array("integer"),
    }, additionalProperties=True),
    "schedule": _field("object", "Schedule rules.", additionalProperties=True),
}

_ROI_FEEDER = {
    **COMMON,
    "padding": _field("number", "Extra padding around a region."),
    "size": _array("integer", "Optional output ROI size."),
    "every_n_frames": _field("integer", "Run once per N frames.", minimum=1, default=1),
}

BUILTIN_MODULE_SCHEMAS: dict[str, dict[str, Any]] = {
    "VideoCaptureOpencv": {"type": "object", "properties": _SOURCE, "additionalProperties": True},
    "VideoCaptureGStreamer": {"type": "object", "properties": _SOURCE, "additionalProperties": True},
    "ObjectDetectorYolo": {"type": "object", "properties": _DETECTOR, "additionalProperties": True},
    "ObjectDetectorRtdetr": {"type": "object", "properties": _DETECTOR, "additionalProperties": True},
    "ObjectDetectorRfdetr": {"type": "object", "properties": _DETECTOR, "additionalProperties": True},
    "ObjectTrackingBotsort": {"type": "object", "properties": _TRACKER, "additionalProperties": True},
    "ObjectMultiCameraTracking": {"type": "object", "properties": {**COMMON, "enable": _field("boolean", default=True)}, "additionalProperties": True},
    "PreprocessingPipeline": {"type": "object", "properties": {**COMMON, "pipeline_file_name": _field("string", "Preprocessing pipeline JSON path."), "in_place_allowed": _field("boolean"), "copy_required": _field("boolean")}, "additionalProperties": True},
    "RoiFeeder": {"type": "object", "properties": _ROI_FEEDER, "additionalProperties": True},
    "AttributeDetector": {"type": "object", "properties": _ATTRIBUTE, "additionalProperties": True},
    "AttributeClassifier": {"type": "object", "properties": _ATTRIBUTE, "additionalProperties": True},
    "CamEventsDetector": {"type": "object", "properties": _EVENT, "additionalProperties": True},
    "ZoneEventsDetector": {"type": "object", "properties": _EVENT, "additionalProperties": True},
    "AttributeEventsDetector": {"type": "object", "properties": _EVENT, "additionalProperties": True},
    "FieldOfViewEventsDetector": {"type": "object", "properties": _EVENT, "additionalProperties": True},
    "SystemEventsDetector": {"type": "object", "properties": _EVENT, "additionalProperties": True},
    "ScheduleAlarmEventsDetector": {"type": "object", "properties": _EVENT, "additionalProperties": True},
}


BUILTIN_MODULE_NAMES: dict[str, tuple[str, str]] = {
    "VideoCaptureOpencv": ("OpenCV source", "Captures frames through OpenCV."),
    "VideoCaptureGStreamer": ("GStreamer source", "Captures frames through GStreamer."),
    "ObjectDetectorYolo": ("YOLO detector", "Detects configured object classes with YOLO."),
    "ObjectDetectorRtdetr": ("RT-DETR detector", "Detects objects with RT-DETR."),
    "ObjectDetectorRfdetr": ("RF-DETR detector", "Detects objects with RF-DETR."),
    "ObjectTrackingBotsort": ("BoT-SORT tracker", "Tracks detections per source."),
    "ObjectMultiCameraTracking": ("Multi-camera tracker", "Associates tracked objects across cameras."),
    "PreprocessingPipeline": ("Preprocessor", "Applies a configured image preprocessing sequence."),
    "RoiFeeder": ("ROI feeder", "Extracts configured object regions for downstream stages."),
    "AttributeDetector": ("Attribute detector", "Detects configured visual attributes."),
    "AttributeClassifier": ("Attribute classifier", "Classifies attributes for tracked objects."),
    "CamEventsDetector": ("Camera events", "Produces camera state events."),
    "ZoneEventsDetector": ("Zone events", "Evaluates object movement against zone rules."),
    "AttributeEventsDetector": ("Attribute events", "Creates events from detected attributes."),
    "FieldOfViewEventsDetector": ("Scheduled alarms (legacy)", "Compatibility identifier for schedule-based alarms."),
    "SystemEventsDetector": ("System events", "Reports system-level alarms."),
    "ScheduleAlarmEventsDetector": ("Scheduled alarms", "Emits configured schedule-based alarms."),
}


BUILTIN_MODULE_STAGES: dict[str, tuple[str, ...]] = {
    "VideoCaptureOpencv": ("sources",),
    "VideoCaptureGStreamer": ("sources",),
    "PreprocessingPipeline": ("preprocessors",),
    "ObjectDetectorYolo": ("detectors",),
    "ObjectDetectorRtdetr": ("detectors",),
    "ObjectDetectorRfdetr": ("detectors",),
    "ObjectTrackingBotsort": ("trackers",),
    "ObjectMultiCameraTracking": ("mc_trackers",),
    "RoiFeeder": ("attributes_roi",),
    "AttributeDetector": ("attributes_roi", "attributes_classifier"),
    "AttributeClassifier": ("attributes_classifier",),
    "CamEventsDetector": ("events_detectors",),
    "ZoneEventsDetector": ("events_detectors",),
    "AttributeEventsDetector": ("events_detectors",),
    "FieldOfViewEventsDetector": ("events_detectors",),
    "SystemEventsDetector": ("events_detectors",),
    "ScheduleAlarmEventsDetector": ("events_detectors",),
}

_PIPELINE_ITEM = _field("array", items={"type": "object", "additionalProperties": True})
_MODULE_OVERRIDE = _field("object", properties={
    "mode": _field("string", enum=["replace", "extend"], default="extend"),
    "items": _PIPELINE_ITEM,
}, additionalProperties=True)

BUILTIN_PIPELINE_SCHEMAS: dict[str, dict[str, Any]] = {
    "PipelineSurveillance": {
        "type": "object",
        "properties": {
            "pipeline_class": _field("string"),
            "sources": _PIPELINE_ITEM,
            "preprocessors": _PIPELINE_ITEM,
            "detectors": _PIPELINE_ITEM,
            "trackers": _PIPELINE_ITEM,
            "mc_trackers": _PIPELINE_ITEM,
            "attributes_roi": _PIPELINE_ITEM,
            "attributes_classifier": _PIPELINE_ITEM,
            "modules": _field("object", properties={
                "sources": _MODULE_OVERRIDE,
                "preprocessors": _MODULE_OVERRIDE,
                "detectors": _MODULE_OVERRIDE,
                "trackers": _MODULE_OVERRIDE,
                "mc_trackers": _MODULE_OVERRIDE,
                "attributes_roi": _MODULE_OVERRIDE,
                "attributes_classifier": _MODULE_OVERRIDE,
            }, additionalProperties=True),
            "detector_fanout_policy": _field("string", enum=["forward_partial", "drop_frame"], default="forward_partial"),
            "detector_fanout_timeout_sec": _field("number", exclusiveMinimum=0),
            "detector_fanout_max_pending": _field("integer", minimum=1),
        },
        "additionalProperties": True,
    },
    "PipelineDeclarative": {
        "type": "object",
        "properties": {
            "pipeline_class": _field("string"),
            "stages": _field("array", items={
                "type": "object",
                "properties": {
                    "name": _field("string"),
                    "kind": _field("string", enum=["source", "frame", "step"]),
                    "items": _PIPELINE_ITEM,
                },
                "additionalProperties": True,
            }),
            "final_results": _field("string", "Name of the stage whose result is published."),
        },
        "additionalProperties": True,
    },
    "PipelineCapture": {
        "type": "object",
        "properties": {
            "pipeline_class": _field("string"),
            "sources": _PIPELINE_ITEM,
        },
        "additionalProperties": True,
    },
}

BUILTIN_PIPELINE_NAMES: dict[str, tuple[str, str]] = {
    "PipelineSurveillance": (
        "Surveillance pipeline",
        "Fixed multi-camera pipeline with explicit frame and event stages.",
    ),
    "PipelineDeclarative": (
        "Declarative pipeline",
        "Linear pipeline assembled from ordered declarative stages.",
    ),
    "PipelineCapture": (
        "Capture pipeline",
        "Simple video-source pipeline for capture and playback workflows.",
    ),
}


def _builtin_topology_provider(pipeline_id: str):
    """Return a lazy provider so metadata registration does not import pipelines."""
    def provider(config: Any):
        from evileye.core.pipeline_topology import (
            build_capture_topology,
            build_declarative_topology,
            build_surveillance_topology,
        )

        builders = {
            "PipelineSurveillance": build_surveillance_topology,
            "PipelineDeclarative": build_declarative_topology,
            "PipelineCapture": build_capture_topology,
        }
        return builders[pipeline_id](config)

    return provider


def builtin_pipeline_metadata(
    pipeline_id: str,
) -> tuple[str | None, str | None, dict[str, Any] | None, Any | None]:
    short_id = str(pipeline_id).split("/", 1)[-1]
    name, description = BUILTIN_PIPELINE_NAMES.get(short_id, (None, None))
    schema = BUILTIN_PIPELINE_SCHEMAS.get(short_id)
    provider = _builtin_topology_provider(short_id) if short_id in BUILTIN_PIPELINE_SCHEMAS else None
    return name, description, schema, provider


def builtin_module_metadata(module_id: str) -> tuple[str | None, str | None, dict[str, Any] | None, tuple[str, ...]]:
    """Return display metadata for a built-in registration without importing it."""
    short_id = str(module_id).split("/", 1)[-1]
    name, description = BUILTIN_MODULE_NAMES.get(short_id, (None, None))
    return name, description, BUILTIN_MODULE_SCHEMAS.get(short_id), BUILTIN_MODULE_STAGES.get(short_id, ())
