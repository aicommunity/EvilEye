from typing import Any
import time

from .processor_base import ProcessorBase
from .frame import Frame
import os
from collections import defaultdict


class ProcessorStep(ProcessorBase):
    def __init__(self, processor_name, class_name, num_processors: int, order: int):
        super().__init__(processor_name, class_name, num_processors, order)
        # Diagnostics for output freshness at stage level.
        # We only need trackers->(mt trackers) freshness, so keep it gated by processor_name.
        self._perf_diag_env = os.getenv("EVILEYE_PERF_DIAG", "").strip().lower() in {"1", "true", "yes", "on"}
        self._perf_diag_every = int(os.getenv("EVILEYE_PERF_DIAG_EVERY", "60") or "60")
        self._pipeline_timeline_env = os.getenv(
            "EVILEYE_PIPELINE_TIMELINE", ""
        ).strip().lower() in {"1", "true", "yes", "on"}
        self._last_stage_timeline: dict[str, Any] = {}
        self._output_perf_diag_counter = 0

        # Input freshness diagnostics (how often inputs are new frame_id per source_id).
        self._input_perf_diag_counter = 0
        self._input_last_frame_id_by_source: dict[int, int | None] = {}
        self._input_updates_by_source: dict[int, int] = defaultdict(int)
        self._input_repeats_by_source: dict[int, int] = defaultdict(int)

        # Output freshness diagnostics for trackers stage (how often trackers outputs are new frame_id).
        self._trackers_last_frame_id_by_source: dict[int, int | None] = {}
        self._trackers_updates_by_source: dict[int, int] = defaultdict(int)
        self._trackers_repeats_by_source: dict[int, int] = defaultdict(int)
        self._mc_tick_diag_counter = 0

    def _append_processing_result(self, processing_results: list, normalized: Any) -> None:
        if normalized is None:
            return
        processing_results.append(normalized)

    def _drain_processor_outputs(
        self, processing_results: list, *, max_items_per_processor: int = 64
    ) -> int:
        """Non-blocking drain of worker output queues (no wall-clock wait)."""
        added = 0
        for processor in self.processors:
            drained = 0
            while drained < max_items_per_processor:
                result = processor.get()
                if not result:
                    break
                normalized = self._normalize_result_meta(result)
                if self._perf_diag_env and self.processor_name == "trackers" and normalized is not None:
                    data = None
                    frame = None
                    if isinstance(normalized, (list, tuple)) and len(normalized) >= 2:
                        data = normalized[0]
                        frame = normalized[1]
                    elif isinstance(normalized, Frame):
                        frame = normalized
                    sid = getattr(data, "source_id", None)
                    if sid is None:
                        sid = getattr(frame, "source_id", None)
                    fid = getattr(data, "frame_id", None)
                    if fid is None:
                        fid = getattr(frame, "frame_id", None)
                    if isinstance(sid, int) and fid is not None:
                        prev_fid = self._trackers_last_frame_id_by_source.get(sid)
                        if fid == prev_fid:
                            self._trackers_repeats_by_source[sid] += 1
                        else:
                            self._trackers_updates_by_source[sid] += 1
                        self._trackers_last_frame_id_by_source[sid] = fid
                self._append_processing_result(processing_results, normalized)
                drained += 1
                added += 1
        return added

    def _adapt_input_for_processor(self, input_item, processor):
        """
        Compatibility adapter between standard and descriptor payloads.
        If stage receives a frame with frame_handle and target processor requires
        materialized image, attempt best-effort materialization.
        """
        data = None
        frame = None
        if isinstance(input_item, (list, tuple)) and len(input_item) >= 2:
            data, frame = input_item[0], input_item[1]
        elif isinstance(input_item, Frame):
            frame = input_item
        else:
            return input_item
        try:
            requires_materialized = bool(
                getattr(processor, "requires_materialized_frame", True)
            )
            if not requires_materialized:
                return input_item
            if getattr(frame, "image", None) is not None:
                return input_item
            frame_handle = getattr(frame, "frame_handle", None)
            if frame_handle is None:
                frame_handle = getattr(frame, "frame_ref", None)
            if frame_handle is None:
                return input_item
            from .frame_transport import SharedFrameTransport
            transport = SharedFrameTransport()
            frame.image = transport.consume_frame(frame_handle)
            try:
                setattr(frame, "frame_handle", None)
                setattr(frame, "frame_ref", None)
            except Exception:
                pass
            if isinstance(input_item, (list, tuple)) and len(input_item) >= 2:
                return [data, frame]
            return frame
        except Exception:
            return input_item

    def _process_mc_trackers_sync(self, input_list) -> list:
        from evileye.core.frame import Frame
        from evileye.object_multi_camera_tracker.custom_object_tracking import (
            ObjectMultiCameraTracking,
        )
        from evileye.object_tracker.tracking_results import TrackingResultList

        if not self.processors:
            return []
        mc = self.processors[0]
        if not isinstance(mc, ObjectMultiCameraTracking):
            raise RuntimeError("mc_trackers expects ObjectMultiCameraTracking")

        batch: dict[int, tuple[TrackingResultList, Frame]] = {}
        for inp in input_list:
            adapted = self._adapt_input_for_processor(inp, mc)
            if not (isinstance(adapted, (list, tuple)) and len(adapted) >= 2):
                continue
            track_info, frame = adapted[0], adapted[1]
            if not isinstance(frame, Frame):
                continue
            if frame.source_id is None:
                continue
            batch[frame.source_id] = (track_info, frame)

        t_mc = time.monotonic()
        emitted = mc.ingest_tick_batch(batch)
        if self._pipeline_timeline_env:
            acc_ages: dict[int, float] = {}
            acc_fids: dict[int, int | None] = {}
            now_ts = time.time()
            for sid, (ti, fr) in mc._accumulated_tick_batch.items():
                ts = mc._timestamp_sec(fr)
                if ts is not None:
                    acc_ages[sid] = round(now_ts - ts, 3)
                acc_fids[sid] = mc._frame_id_for_pair(ti, fr)
            batch_fids = {
                int(sid): mc._frame_id_for_pair(ti, fr)
                for sid, (ti, fr) in batch.items()
            }
            self._last_stage_timeline = {
                "stage": "mc_trackers",
                "batch_in": len(batch),
                "emitted": len(emitted or []),
                "accumulator": f"{len(mc._accumulated_tick_batch)}/{len(mc.source_ids)}",
                "batch_frame_ids": batch_fids,
                "acc_frame_ids": acc_fids,
                "acc_age_sec": acc_ages,
                "skip": mc._diag_tick_batch_skip,
                "stale_evict": mc._diag_tick_batch_stale_evict,
                "ingest_ms": (time.monotonic() - t_mc) * 1000.0,
            }
            try:
                self.logger.info(
                    "PipelineTimeline(mc_trackers): batch_in=%d emitted=%d acc=%s "
                    "batch_fid=%s acc_fid=%s acc_age_sec=%s skip=%d stale_evict=%d ingest_ms=%.1f",
                    len(batch),
                    len(emitted or []),
                    self._last_stage_timeline["accumulator"],
                    batch_fids,
                    acc_fids,
                    acc_ages,
                    mc._diag_tick_batch_skip,
                    mc._diag_tick_batch_stale_evict,
                    self._last_stage_timeline["ingest_ms"],
                )
            except Exception:
                pass
        if self._perf_diag_env:
            self._mc_tick_diag_counter += 1
            every = max(1, int(self._perf_diag_every or 60))
            if (self._mc_tick_diag_counter % every) == 0:
                try:
                    acc = len(mc._accumulated_tick_batch)
                    self.logger.info(
                        "PerfDiag(MCStep): tick=%d batch_in=%d emitted=%d "
                        "accumulator=%d/%d skip=%d stale_evict=%d",
                        self._mc_tick_diag_counter,
                        len(batch),
                        len(emitted or []),
                        acc,
                        len(mc.source_ids),
                        mc._diag_tick_batch_skip,
                        mc._diag_tick_batch_stale_evict,
                    )
                except Exception:
                    pass
        processing_results = []
        for item in emitted or []:
            processing_results.append(self._normalize_result_meta(item))
        return processing_results

    @staticmethod
    def _normalize_result_meta(result):
        try:
            if not (isinstance(result, (list, tuple)) and len(result) >= 2):
                return result
            data = result[0]
            frame = result[1]
            if data is None or frame is None:
                return result
            if hasattr(data, "source_id") and hasattr(frame, "source_id"):
                data.source_id = frame.source_id
            if hasattr(data, "frame_id") and hasattr(frame, "frame_id"):
                data.frame_id = frame.frame_id
            if hasattr(data, "time_stamp") and hasattr(frame, "time_stamp"):
                data.time_stamp = frame.time_stamp
        except Exception:
            pass
        return result

    def process(self, input_list=None):
        if self.processor_name == "mc_trackers" and input_list is not None:
            return self._process_mc_trackers_sync(input_list)

        processing_results = []
        had_puts = False
        put_count = 0
        stage_had_input = bool(input_list)
        t_stage = time.monotonic()
        # Do not drain before put: stale MP results would be forwarded downstream in the
        # same pipeline.process() pass (e.g. empty tracker rows into mc_trackers).
        if input_list is not None:
            for input in input_list:
                is_processor_found = False
                if (type(input) == list or type(input) == tuple) and len(input) >= 2:
                    data = input[0]
                    frame = input[1]
                elif type(input) == Frame:
                    frame = input
                    data = None
                else:
                    raise RuntimeError(f"Wrong type for input data in processor: {self.class_name}")

                source_id = frame.source_id
                if source_id is not None:
                    try:
                        source_id = int(source_id)
                    except (TypeError, ValueError):
                        source_id = None

                for processor in self.processors:
                    source_ids = processor.get_source_ids()
                    if source_id is not None and source_id in source_ids:
                        processor.put(self._adapt_input_for_processor(input, processor))
                        is_processor_found = True
                        had_puts = True
                        put_count += 1

                    if is_processor_found:
                        break

                if not is_processor_found:
                    res = self.dummy_processor.ResultType()
                    if res is not None:
                        if hasattr(res, "source_id"):
                            setattr(res, "source_id", frame.source_id)
                        if hasattr(res, "frame_id"):
                            setattr(res, "frame_id", frame.frame_id)
                        if hasattr(res, "time_stamp"):
                            setattr(res, "time_stamp", frame.time_stamp)
                        if hasattr(res, "generate_from"):
                            res.generate_from(data)

                    processing_results.append([res, frame])

                # Input freshness counters (detectors/trackers inputs).
                if (
                    is_processor_found
                    and self._perf_diag_env
                    and self.processor_name in {"detectors", "trackers"}
                ):
                    sid = source_id
                    fid = getattr(frame, "frame_id", None)
                    if isinstance(sid, int) and fid is not None:
                        prev_fid = self._input_last_frame_id_by_source.get(sid)
                        if fid == prev_fid:
                            self._input_repeats_by_source[sid] += 1
                        else:
                            self._input_updates_by_source[sid] += 1
                        self._input_last_frame_id_by_source[sid] = fid

        t_after_put = time.monotonic()
        post_drain_added = self._drain_processor_outputs(processing_results)
        t_after_drain = time.monotonic()
        drain_imm_count = len(processing_results)
        t_stage_end = time.monotonic()

        if self._pipeline_timeline_env:
            self._last_stage_timeline = {
                "stage": self.processor_name,
                "in_count": len(input_list) if input_list is not None else 0,
                "put_count": put_count,
                "out_count": len(processing_results),
                "post_drain": post_drain_added,
                "drain_imm_count": drain_imm_count,
                "put_ms": (t_after_put - t_stage) * 1000.0,
                "drain_imm_ms": (t_after_drain - t_after_put) * 1000.0,
                "total_ms": (t_stage_end - t_stage) * 1000.0,
            }
            try:
                self.logger.info(
                    "PipelineTimeline(%s): in=%d put=%d out=%d "
                    "post_drain=%d "
                    "put_ms=%.1f drain_imm_ms=%.1f(out_imm=%d) total_ms=%.1f",
                    self.processor_name,
                    self._last_stage_timeline["in_count"],
                    put_count,
                    self._last_stage_timeline["out_count"],
                    post_drain_added,
                    self._last_stage_timeline["put_ms"],
                    self._last_stage_timeline["drain_imm_ms"],
                    drain_imm_count,
                    self._last_stage_timeline["total_ms"],
                )
            except Exception:
                pass

        # Periodic log for trackers output freshness.
        if self._perf_diag_env and self.processor_name == "trackers":
            self._output_perf_diag_counter += 1
            every = max(1, int(self._perf_diag_every or 60))
            if (self._output_perf_diag_counter % every) == 0:
                try:
                    # Convert defaultdict->dict for cleaner logs.
                    updates = dict(self._trackers_updates_by_source)
                    repeats = dict(self._trackers_repeats_by_source)
                    if updates or repeats:
                        self.logger.info(
                            "PerfDiag(TrackersOut): window=%d updates=%s repeats=%s",
                            self._output_perf_diag_counter,
                            updates,
                            repeats,
                        )
                    else:
                        self.logger.info(
                            "PerfDiag(TrackersOut): window=%d updates={} repeats={}",
                            self._output_perf_diag_counter,
                        )
                except Exception:
                    pass
                self._trackers_updates_by_source = defaultdict(int)
                self._trackers_repeats_by_source = defaultdict(int)

        # Periodic log for detectors/trackers input freshness.
        if self._perf_diag_env and self.processor_name in {"detectors", "trackers"}:
            self._input_perf_diag_counter += 1
            every = max(1, int(self._perf_diag_every or 60))
            if (self._input_perf_diag_counter % every) == 0:
                try:
                    updates = dict(self._input_updates_by_source)
                    repeats = dict(self._input_repeats_by_source)
                    stage = "DetectorsIn" if self.processor_name == "detectors" else "TrackersIn"
                    if updates or repeats:
                        self.logger.info(
                            f"PerfDiag({stage}): window=%d updates=%s repeats=%s",
                            self._input_perf_diag_counter,
                            updates,
                            repeats,
                        )
                    else:
                        self.logger.info(
                            f"PerfDiag({stage}): window=%d updates={{}} repeats={{}}",
                            self._input_perf_diag_counter,
                        )
                except Exception:
                    pass
                self._input_updates_by_source = defaultdict(int)
                self._input_repeats_by_source = defaultdict(int)

        return processing_results
