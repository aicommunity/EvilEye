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
            frame.image = transport.get_frame_view(frame_handle)
            try:
                transport.release_frame(frame_handle)
            except Exception:
                pass
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

    def process(self, input_list=None):
        processing_results = []
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

                for processor in self.processors:
                    source_ids = processor.get_source_ids()
                    if frame.source_id in source_ids:
                        processor.put(self._adapt_input_for_processor(input, processor))
                        is_processor_found = True

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
                if self._perf_diag_env and self.processor_name in {"detectors", "trackers"}:
                    sid = getattr(frame, "source_id", None)
                    fid = getattr(frame, "frame_id", None)
                    if isinstance(sid, int) and fid is not None:
                        prev_fid = self._input_last_frame_id_by_source.get(sid)
                        if fid == prev_fid:
                            self._input_repeats_by_source[sid] += 1
                        else:
                            self._input_updates_by_source[sid] += 1
                        self._input_last_frame_id_by_source[sid] = fid

        def _normalize_result_meta(result):
            """
            Ensure result metadata matches the paired frame.
            Contract for downstream (ObjectsHandler/Visualizer): if result is (data, Frame),
            then data.source_id/frame_id/time_stamp must equal Frame.source_id/frame_id/time_stamp when those attrs exist.
            """
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

        # Drain outputs from all processors.
        # Previously output queues were effectively unbounded so slow draining didn't surface as "queue full"
        # (but could accumulate memory). Now that outputs are bounded, we must drain more than 1 item per tick.
        max_items_per_processor = 64
        for processor in self.processors:
            drained = 0
            while drained < max_items_per_processor:
                result = processor.get()
                if not result:
                    break

                normalized = _normalize_result_meta(result)
                # Stage-specific freshness diagnostics: how often trackers emit new frame_id per source.
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

                processing_results.append(normalized)
                drained += 1

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