from typing import Any
import time
import copy

from .processor_base import ProcessorBase
from .frame import Frame
import os
from collections import defaultdict


class ProcessorStep(ProcessorBase):
    def __init__(
        self,
        processor_name,
        class_name,
        num_processors: int,
        order: int,
        class_names: list[str] | None = None,
    ):
        super().__init__(
            processor_name, class_name, num_processors, order, class_names=class_names
        )
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
        self._mp_pending_snapshot = 0
        self._detector_fanout_pending: dict[tuple[int, int, int], dict[str, Any]] = {}
        self._detector_fanout_timeout_sec = float(
            os.getenv("EVILEYE_DETECTOR_FANOUT_TIMEOUT_SEC", "30")
        )
        if self._detector_fanout_timeout_sec <= 0:
            raise ValueError("EVILEYE_DETECTOR_FANOUT_TIMEOUT_SEC must be positive")
        self._detector_fanout_max_pending = 512
        self._detector_fanout_incomplete_count = 0
        self._detector_fanout_dropped_count = 0
        self.detector_fanout_policy = "forward_partial"

    def set_detector_fanout_policy(self, policy: str) -> None:
        policy = str(policy).strip().lower()
        if policy not in {"forward_partial", "drop_frame"}:
            raise ValueError(
                "detector_fanout_policy must be 'forward_partial' or 'drop_frame'"
            )
        self.detector_fanout_policy = policy

    def _append_processing_result(self, processing_results: list, normalized: Any) -> None:
        if normalized is None:
            return
        processing_results.append(normalized)

    @staticmethod
    def _merge_detector_fanout(results: list) -> list:
        """Merge compatible detector result lists for the same source/frame."""
        merged_results = []
        by_frame: dict[tuple[int, int, int], int] = {}
        for result in results:
            if not isinstance(result, (list, tuple)) or len(result) < 2:
                merged_results.append(result)
                continue
            data, frame = result[0], result[1]
            source_id = getattr(frame, "source_id", None)
            frame_id = getattr(frame, "frame_id", None)
            if source_id is None or frame_id is None:
                merged_results.append(result)
                continue
            try:
                generation = int(getattr(frame, "connection_generation", 0) or 0)
                key = (int(source_id), generation, int(frame_id))
            except (TypeError, ValueError):
                merged_results.append(result)
                continue
            detections = data.get("detections") if isinstance(data, dict) else getattr(data, "detections", None)
            if not isinstance(detections, list):
                merged_results.append(result)
                continue
            existing_idx = by_frame.get(key)
            if existing_idx is None:
                try:
                    data_copy = dict(data) if isinstance(data, dict) else copy.copy(data)
                    copied_detections = list(detections)
                    if isinstance(data_copy, dict):
                        data_copy["detections"] = copied_detections
                    else:
                        data_copy.detections = copied_detections
                except Exception:
                    merged_results.append(result)
                    continue
                by_frame[key] = len(merged_results)
                merged_results.append([data_copy, frame])
                continue
            base_data = merged_results[existing_idx][0]
            if isinstance(base_data, dict):
                base_data["detections"].extend(detections)
            else:
                base_data.detections.extend(detections)
        return merged_results

    @staticmethod
    def _detector_frame_key(item):
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            frame = item[1]
        else:
            frame = item
        source_id = getattr(frame, "source_id", None)
        frame_id = getattr(frame, "frame_id", None)
        if source_id is None or frame_id is None:
            return None
        try:
            generation = int(getattr(frame, "connection_generation", 0) or 0)
            return int(source_id), generation, int(frame_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _processor_has_pending_work(processor) -> bool:
        has_pending = getattr(processor, "has_pending_work", None)
        if callable(has_pending):
            try:
                return bool(has_pending())
            except Exception:
                return True
        get_stats = getattr(processor, "get_runtime_stats", None)
        if callable(get_stats):
            try:
                return int(get_stats().get("in_flight", 0) or 0) > 0
            except Exception:
                return True
        return True

    def _collect_detector_fanout_outputs(
        self, passthrough: list, outputs_by_processor: dict[int, list]
    ) -> list:
        emitted = list(passthrough)
        for processor_index, results in outputs_by_processor.items():
            for result in results:
                key = self._detector_frame_key(result)
                state = self._detector_fanout_pending.get(key) if key is not None else None
                if state is None or processor_index not in state["expected"]:
                    emitted.append(result)
                    continue
                state["results"].append(result)
                state["received"].add(processor_index)

        now = time.monotonic()
        pending_keys = list(self._detector_fanout_pending)
        overflow_count = max(0, len(pending_keys) - self._detector_fanout_max_pending)
        overflow_keys = set(pending_keys[:overflow_count])
        for key in pending_keys:
            state = self._detector_fanout_pending.get(key)
            if state is None:
                continue
            missing = state["expected"] - state["received"]
            expired = now - state["created_at"] >= self._detector_fanout_timeout_sec
            missing_modules_idle = bool(missing) and all(
                not self._processor_has_pending_work(self.processors[index])
                for index in missing
            )
            overflowed = key in overflow_keys
            if missing and not expired and not missing_modules_idle and not overflowed:
                continue
            if missing:
                missing_ids = [
                    f"{getattr(self.processors[index], 'module_id', self.class_name)}[{index}]"
                    for index in sorted(missing)
                ]
                self._detector_fanout_incomplete_count += 1
                drop_frame = self.detector_fanout_policy == "drop_frame"
                if drop_frame:
                    self._detector_fanout_dropped_count += 1
                action = "dropping" if drop_frame else "forwarding"
                self.logger.warning(
                    "Detector fanout incomplete for source=%s generation=%s frame=%s; "
                    "missing=%s; %s %d available result(s)%s",
                    key[0],
                    key[1],
                    key[2],
                    missing_ids,
                    action,
                    len(state["results"]),
                    (
                        " (pending limit reached)"
                        if overflowed
                        else " (timeout)"
                        if expired
                        else " (worker completed without output)"
                    ),
                )
            if not (missing and self.detector_fanout_policy == "drop_frame"):
                emitted.extend(self._merge_detector_fanout(state["results"]))
            del self._detector_fanout_pending[key]

        return self._merge_detector_fanout(emitted)

    def _sync_mp_mode(self) -> str:
        return os.getenv("EVILEYE_PIPELINE_SYNC_MP", "").strip().lower()

    def _sync_mp_enabled(self) -> bool:
        return self._sync_mp_mode() in {
            "1",
            "true",
            "yes",
            "on",
            "adaptive",
            "conditional",
        }

    def _sync_mp_adaptive(self) -> bool:
        return self._sync_mp_mode() in {"adaptive", "conditional"}

    def _drain_max_items(self) -> int:
        try:
            return max(1, int(os.getenv("EVILEYE_MP_DRAIN_MAX_ITEMS", "64") or "64"))
        except (TypeError, ValueError):
            return 64

    def _sync_mp_drain_after_put(
        self, processing_results: list, *, detector_outputs: dict[int, list] | None = None
    ) -> int:
        if not self._sync_mp_enabled():
            return 0
        if self._sync_mp_adaptive():
            pending = int(getattr(self, "_mp_pending_snapshot", 0) or 0)
            try:
                num_sources = int(os.getenv("EVILEYE_SYNC_MP_NUM_SOURCES", "5") or "5")
            except (TypeError, ValueError):
                num_sources = 5
            default_cap = 2 * num_sources
            try:
                cap = int(
                    os.getenv("EVILEYE_SYNC_MP_PENDING_MAX", str(default_cap)) or str(default_cap)
                )
            except (TypeError, ValueError):
                cap = default_cap
            if pending >= cap:
                return 0
        if self.processor_name not in {"detectors", "trackers"}:
            return 0
        from .mp_stage import MpStageProcessor
        from .processor_base import EXEC_MODE_PROCESS

        has_mp = False
        for processor in self.processors:
            if (
                isinstance(processor, MpStageProcessor)
                and processor.execution_mode == EXEC_MODE_PROCESS
            ):
                has_mp = True
                break
        if not has_mp:
            return 0
        try:
            sync_ms = float(os.getenv("EVILEYE_PIPELINE_SYNC_MP_MS", "8") or "8")
        except (TypeError, ValueError):
            sync_ms = 8.0
        deadline = time.monotonic() + max(0.001, sync_ms / 1000.0)
        added = 0
        while time.monotonic() < deadline:
            n = self._drain_processor_outputs(
                processing_results,
                max_items_per_processor=self._drain_max_items(),
                detector_outputs=detector_outputs,
            )
            added += n
            if n > 0:
                break
            time.sleep(0.001)
        return added

    def _drain_processor_outputs(
        self,
        processing_results: list,
        *,
        max_items_per_processor: int = 64,
        detector_outputs: dict[int, list] | None = None,
    ) -> int:
        """Non-blocking drain of worker output queues (no wall-clock wait)."""
        added = 0
        for processor_index, processor in enumerate(self.processors):
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
                if detector_outputs is not None:
                    detector_outputs.setdefault(processor_index, []).append(normalized)
                else:
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
            materialized = transport.consume_frame(frame_handle)
            if materialized is None or getattr(materialized, "size", 0) == 0:
                return input_item
            frame.image = materialized
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
        from evileye.object_tracker.tracking_results import TrackingResultList

        if not self.processors:
            return []
        mc = self.processors[0]
        if not callable(getattr(mc, "process_batch", None)):
            raise RuntimeError(
                "mc_trackers expects a batch_processor implementing process_batch(batch, state)"
            )

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
        emitted = mc.process_batch(batch)
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
        from .stage_result_normalizer import normalize_result_meta

        return normalize_result_meta(result)

    def process(self, input_list=None):
        if self.processor_name == "mc_trackers" and input_list is not None:
            return self._process_mc_trackers_sync(input_list)

        processing_results = []
        detector_outputs = {} if self.processor_name == "detectors" else None
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

                detector_targets = set()
                for processor_index, processor in enumerate(self.processors):
                    source_ids = processor.get_source_ids()
                    if source_id is not None and (source_ids is None or source_id in source_ids):
                        processor.put(self._adapt_input_for_processor(input, processor))
                        is_processor_found = True
                        had_puts = True
                        put_count += 1
                        if detector_outputs is not None:
                            detector_targets.add(processor_index)

                if len(detector_targets) > 1:
                    key = self._detector_frame_key(frame)
                    if key is not None:
                        state = self._detector_fanout_pending.setdefault(
                            key,
                            {
                                "expected": set(),
                                "received": set(),
                                "results": [],
                                "created_at": time.monotonic(),
                            },
                        )
                        state["expected"].update(detector_targets)

                if not is_processor_found:
                    result_type = getattr(self.dummy_processor, "ResultType", None)
                    if callable(result_type):
                        res = result_type()
                    elif self.processor_name == "detectors":
                        from evileye.object_detector.object_detection_base import DetectionResultList

                        res = DetectionResultList()
                    elif self.processor_name in {"trackers", "mc_trackers"}:
                        from evileye.object_tracker.tracking_results import TrackingResultList

                        res = TrackingResultList()
                    else:
                        # A generic plugin may not expose the legacy ResultType
                        # class. Preserve the upstream item when this plugin is
                        # not assigned to the current source.
                        processing_results.append(input)
                        continue
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
        post_drain_added = self._drain_processor_outputs(
            processing_results,
            max_items_per_processor=self._drain_max_items(),
            detector_outputs=detector_outputs,
        )
        post_drain_added += self._sync_mp_drain_after_put(
            processing_results, detector_outputs=detector_outputs
        )
        if detector_outputs is not None:
            processing_results = self._collect_detector_fanout_outputs(
                processing_results, detector_outputs
            )
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
