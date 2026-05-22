# Code module index (EvilEye)

One-page map of `evileye/` packages. MP-specific modules: see also [thread_vs_mp_contracts.md §15](thread_vs_mp_contracts.md#15-модульный-индекс-mp-post-refactor).

## evileye/core/

| Module | Entry / role | Thread/MP |
|--------|--------------|-----------|
| pipeline_processors.py | `PipelineProcessors.process` tick | Both |
| processor_step.py | Per-stage drain, sync MP env | Both |
| pipeline_surveillance.py | Surveillance wiring, `estimate_mp_backlog_stats` | Both |
| mp_async_bridge.py | FIFO pending + put policy | MP |
| mp_pending_jobs.py | `DetectorPendingJob`, `TrackerPendingJob` | MP |
| mp_stage.py | `MpPendingReporter`, `MpStageProcessor` protocols | MP |
| mp_queue_config.py | Queue sizes, drain poll, pending caps | MP |
| stage_result_normalizer.py | `(data, frame)` for ProcessorStep | Both |
| frame_worker_meta.py | Pack/unpack frame for MP worker | MP |
| execution_backend.py | Detector/tracker backend factory (S5) | Both |
| dual_mode_processor.py | Skeleton base (S1, not adopted) | MP |
| processor_base.py | `EvilEyeBase.register` factory | Both |

## evileye/capture/

| Module | Entry | Thread/MP |
|--------|-------|-----------|
| video_capture_gstreamer.py | `VideoCaptureGStreamer` | Both (`execution_mode`) |
| video_capture_opencv.py | `VideoCaptureOpencv` | Thread typical |
| mp_worker_capture.py | GStreamer child worker | MP |
| queue_policy.py | drop-oldest deque + MP queues | MP |

## evileye/object_detector/

| Module | Entry | Thread/MP |
|--------|-------|-----------|
| object_detection_yolo.py | `ObjectDetectorYolo` (primary) | Both |
| object_detection_yolo_mp.py | Legacy `ObjectDetectorYoloMp` | MP legacy |
| detection_thread_yolo.py | Thread path + `YoloRuntime` | Thread |
| detection_thread_yolo_mp.py | Feed/drain + `MpAsyncBridge` | MP |
| mp_worker_yolo.py | Child YOLO worker | MP |
| yolo_runtime.py | Shared inference (thread + worker) | Both |
| detection_preprocess.py | ROI split (DUP-003 closed) | Both |

## evileye/object_tracker/

| Module | Entry | Thread/MP |
|--------|-------|-----------|
| object_tracking_botsort.py | BoT-SORT facade | Both |
| object_tracking_base.py | Process feed/drain + bridge | MP |
| mp_worker_tracker.py | Child tracker + encoder | MP |
| track_update_core.py | Shared BoT-SORT update (R6) | Both |

## evileye/object_multi_camera_tracker/

| Module | Entry | Thread/MP |
|--------|-------|-----------|
| custom_object_tracking.py | `ObjectMultiCameraTracking` | Sync batch only (no process mode) |

## evileye/attributes_detection/

| Module | Entry | Thread/MP |
|--------|-------|-----------|
| attribute_classifier.py | Attributes + `YoloRuntime` | RPC / process worker |
| mp_worker_attribute_classifier.py | Child classifier | MP |

## evileye/controller/

| Module | Entry | Thread/MP |
|--------|-------|-----------|
| controller.py | Main loop, backpressure env | Both |

## evileye/pipelines/

| Module | Entry | Thread/MP |
|--------|-------|-----------|
| pipeline_surveillance.py | Processor graph | Both |
