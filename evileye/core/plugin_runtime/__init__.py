"""Runtime adapters that run plugin modules inside the EvilEye pipeline.

The implementation is split by module family; this package re-exports every name
that used to live in the single ``evileye.core.plugin_runtime`` module."""

from .transport import (
    _FRAME_METADATA_FIELDS,
    _FRAME_RUNTIME_KEY,
    _IncomingFrameDropped,
    _PROCESS_INPUT_MARKER,
    _PROCESS_OUTPUT_MARKER,
    _PROCESS_RESULT_MARKER,
    _call_factory,
    _close_item_resources,
    _create_state,
    _get_model_class_mapping,
    _is_frame_work_item,
    _normalize_model_class_mapping,
    _prepare_item_for_process,
    _request_id_from_process_payload,
    _restore_process_result,
    _serialize_process_value,
    _validate_model_class_mapping_capability,
)
from .item import (
    ItemModuleAdapter,
    ItemModuleWorker,
    _ERROR_POLICIES,
    _ERROR_POLICY_PARAMS,
    _ItemErrorPolicy,
    _ItemErrorTracker,
)
from .parallel import (
    OrderedItemModuleWorker,
    ParallelItemModuleAdapter,
    _ORDERED_EVICTED,
    _ORDERED_SKIP,
    _ORDERED_THREAD_OUTPUT_MARKER,
)
from .batch import BatchProcessorModuleAdapter
from .legacy import LegacyProcessorModuleAdapter
from .events import (
    EventDetectorModuleAdapter,
    EventDetectorUpdateWorker,
    _EVENT_UPDATE_INPUT,
    _EVENT_UPDATE_OUTPUT,
)
from .source import SourceModuleAdapter, _SOURCE_ITEM_MARKER, _source_worker_entry

__all__ = [
    "BatchProcessorModuleAdapter",
    "EventDetectorModuleAdapter",
    "EventDetectorUpdateWorker",
    "ItemModuleAdapter",
    "ItemModuleWorker",
    "LegacyProcessorModuleAdapter",
    "OrderedItemModuleWorker",
    "ParallelItemModuleAdapter",
    "SourceModuleAdapter",
    "_ERROR_POLICIES",
    "_ERROR_POLICY_PARAMS",
    "_EVENT_UPDATE_INPUT",
    "_EVENT_UPDATE_OUTPUT",
    "_FRAME_METADATA_FIELDS",
    "_FRAME_RUNTIME_KEY",
    "_IncomingFrameDropped",
    "_ItemErrorPolicy",
    "_ItemErrorTracker",
    "_ORDERED_EVICTED",
    "_ORDERED_SKIP",
    "_ORDERED_THREAD_OUTPUT_MARKER",
    "_PROCESS_INPUT_MARKER",
    "_PROCESS_OUTPUT_MARKER",
    "_PROCESS_RESULT_MARKER",
    "_SOURCE_ITEM_MARKER",
    "_call_factory",
    "_close_item_resources",
    "_create_state",
    "_get_model_class_mapping",
    "_is_frame_work_item",
    "_normalize_model_class_mapping",
    "_prepare_item_for_process",
    "_request_id_from_process_payload",
    "_restore_process_result",
    "_serialize_process_value",
    "_source_worker_entry",
    "_validate_model_class_mapping_capability",
]
