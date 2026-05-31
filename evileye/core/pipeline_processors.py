from .pipeline_base import PipelineBase
from .processor_source import ProcessorSource
from .processor_frame import ProcessorFrame
from .processor_step import ProcessorStep
from .processor_base import ProcessorBase
from abc import abstractmethod
from typing import List, Dict, Any, Optional, Tuple
import threading
import os


class PipelineProcessors(PipelineBase):
    """
    Processor-based pipeline implementation.
    Manages multiple processors in a processing chain.
    """

    def __init__(self):
        super().__init__()

        # List of processor components in execution order
        self.processors: List[ProcessorBase] = []

        # Unified processor parameters storage: {processor_name: params_list}
        self._processor_params: Dict[str, List[Dict]] = {}

        # Encoders for tracking (can be overridden by derived classes)
        self.encoders: Dict[str, Any] = {}

        self.sources_proc: ProcessorSource | None = None

        self._final_results_name = ""
        self._ipc_mode = "standard"

        # Perf diagnostics (disabled by default). Enable with env EVILEYE_PERF_DIAG=1
        # or via controller.perf_diag=true (checked in Controller).
        import os
        self._perf_diag_env = os.getenv("EVILEYE_PERF_DIAG", "").strip().lower() in {"1", "true", "yes", "on"}
        self._perf_diag_every = int(os.getenv("EVILEYE_PERF_DIAG_EVERY", "60") or "60")
        self._perf_diag_loop = 0

    def default(self):
        """Reset pipeline to default state"""
        super().default()
        self._processor_params = {}
        self.encoders = {}
        self.processors = []

    def set_credentials(self, credentials):
        """Set credentials for pipeline components"""
        super().set_credentials(credentials)

    def init_impl(self, **kwargs):
        """Initialize pipeline implementation with processors - override in subclasses"""
        # Derived classes should implement their own initialization logic
        return True

    def release_impl(self):
        """Release all pipeline processors in reverse order"""
        for processor in reversed(self.processors):
            if processor is not None:
                processor.release()

    def reset_impl(self):
        """Reset pipeline state"""
        # Default implementation - override in subclasses if needed
        return None

    def set_params_impl(self):
        """Set pipeline parameters from self.params - override in subclasses"""
        self._ipc_mode = str(self.params.get("ipc_mode", "standard") or "standard")
        for section_name in self.params:
            if section_name in {"pipeline_class", "ipc_mode"}:
                continue
            section_params = self.params.get(section_name, []) or []
            self._processor_params[section_name] = section_params

    def get_params_impl(self):
        """Get parameters from all processors"""
        params = super().get_params_impl()

        # Get parameters from each processor type
        for processor in self.processors:
            if processor is not None:
                section_name = processor.get_name()
                params[section_name] = processor.get_params()

        return params

    def start(self):
        """Start all processors in order, with sources starting last to prevent queue overflow"""
        import time
        from ..object_detector.object_detection_base import ObjectDetectorBase
        from .processor_frame import ProcessorFrame

        # First, start all processors except sources (detectors, trackers, etc.)
        # This ensures they are ready to receive data before sources begin capturing
        detectors = []
        for processor in self.processors:
            if processor is not None and not isinstance(processor, ProcessorSource):
                processor.start()
                # Collect detectors to wait for model loading
                if isinstance(processor, ProcessorFrame):
                    # Check if this processor contains detectors
                    if hasattr(processor, 'processors'):
                        for p in processor.processors:
                            if isinstance(p, ObjectDetectorBase):
                                detectors.append(p)

        # Do not block pipeline startup for a long time on detector readiness.
        # In headless/API runs this delays controller.start(), which in turn
        # prevents preview publication and may look like a hung runtime.
        # We only do a short best-effort readiness wait here.
        if detectors:
            self.logger.info(f"Waiting for {len(detectors)} detector(s) to load models...")
            all_ready = True
            # Wait in parallel so total wait is bounded and short.
            detectors_with_ready = [d for d in detectors if hasattr(d, "is_ready")]
            detectors_fallback = [d for d in detectors if not hasattr(d, "is_ready")]
            if detectors_with_ready:
                import concurrent.futures
                timeout_per_detector = 2.0
                with concurrent.futures.ThreadPoolExecutor(
                        max_workers=min(len(detectors_with_ready), 8)
                ) as executor:
                    future_to_det = {
                        executor.submit(d.is_ready, timeout_per_detector): d
                        for d in detectors_with_ready
                    }
                    try:
                        for fut in concurrent.futures.as_completed(
                                future_to_det, timeout=timeout_per_detector + 1.0
                        ):
                            det = future_to_det[fut]
                            try:
                                ready = fut.result()
                            except Exception as e:
                                ready = False
                                self.logger.warning(
                                    f"Detector {det.__class__.__name__} is_ready raised: {e}"
                                )
                            if not ready:
                                self.logger.warning(
                                    f"Detector {det.__class__.__name__} did not become ready within timeout"
                                )
                                all_ready = False
                            else:
                                self.logger.debug(f"Detector {det.__class__.__name__} is ready")
                    except concurrent.futures.TimeoutError:
                        all_ready = False
                        self.logger.warning("Detector readiness wait timed out; continuing startup")
            for _ in detectors_fallback:
                time.sleep(0.2)
            if all_ready:
                self.logger.info("All detectors are ready")
            else:
                self.logger.warning("Some detectors may not be fully ready, but starting sources anyway")
            # Small settling delay without stalling startup for tens of seconds.
            time.sleep(0.1)
        else:
            time.sleep(0.1)

        # Finally, start sources last so they don't send frames before processors are ready
        for processor in self.processors:
            if processor is not None and isinstance(processor, ProcessorSource):
                processor.start()

    def stop(self):
        """Stop all processors in reverse order"""
        stop_timeout_sec = float(
            os.getenv("EVILEYE_PROCESSOR_STOP_TIMEOUT_SEC", "8.0") or "8.0"
        )
        source_processors = [p for p in self.processors if p is not None and isinstance(p, ProcessorSource)]
        other_processors = [p for p in reversed(self.processors) if
                            p is not None and not isinstance(p, ProcessorSource)]
        for processor in [*source_processors, *other_processors]:
            if processor is not None:
                stop_done = threading.Event()
                stop_error: list[Exception] = []

                def _stop_processor():
                    try:
                        processor.stop()
                    except Exception as exc:
                        stop_error.append(exc)
                    finally:
                        stop_done.set()

                threading.Thread(target=_stop_processor, daemon=True).start()
                if not stop_done.wait(stop_timeout_sec):
                    self.logger.warning(
                        "Processor stop timeout after %.1fs: %s",
                        stop_timeout_sec,
                        processor.__class__.__name__,
                    )
                    continue
                if stop_error:
                    raise stop_error[0]

    def check_all_sources_finished(self):
        if self.sources_proc is None:
            return True
        return self.sources_proc.check_all_sources_finished()

    def process(self) -> dict[Any, Any]:
        pipeline_results = dict()
        step_result = None
        tracking_results = None  # Store tracking results for attributes processors
        perf_diag_enabled = self._perf_diag_env
        timeline_enabled = os.getenv(
            "EVILEYE_PIPELINE_TIMELINE", ""
        ).strip().lower() in {"1", "true", "yes", "on"}
        if perf_diag_enabled or timeline_enabled:
            from timeit import default_timer as _t
            t_begin = _t()
            stage_timings = []

        mp_pending_snapshot = 0
        try:
            estimate_stats = getattr(self, "estimate_mp_backlog_stats", None)
            if callable(estimate_stats):
                stats = estimate_stats()
                mp_pending_snapshot = int(stats.get("pending", 0))
            else:
                estimate_legacy = getattr(self, "estimate_mp_pending_depth", None)
                if callable(estimate_legacy):
                    pending, _ = estimate_legacy()
                    mp_pending_snapshot = int(pending)
        except Exception:
            pass

        for processor in self.processors:
            if processor is None:
                continue

            if isinstance(processor, ProcessorSource):
                self.run_sources()

            if isinstance(processor, ProcessorStep):
                processor._mp_pending_snapshot = mp_pending_snapshot

            if perf_diag_enabled or timeline_enabled:
                t0 = _t()
            step_result = processor.process(step_result)
            if perf_diag_enabled or timeline_enabled:
                t1 = _t()
                try:
                    out_len = len(step_result) if step_result is not None else 0
                except Exception:
                    out_len = -1
                stage_timings.append((processor.get_name(), (t1 - t0) * 1000.0, out_len))

            pipeline_results[processor.get_name()] = step_result

            # Store tracking results for attributes processors
            # Always use mc_trackers results for attributes, regardless of mc_trackers status
            if processor.get_name() == 'mc_trackers' and step_result is not None:
                tracking_results = step_result

        # Store results for external access
        if pipeline_results:
            self.add_result(pipeline_results)

        if perf_diag_enabled or timeline_enabled:
            self._perf_diag_loop += 1
            every = max(1, int(self._perf_diag_every or 60))
            log_this_tick = timeline_enabled or (
                perf_diag_enabled and (self._perf_diag_loop % every) == 0
            )
            if log_this_tick:
                try:
                    total_ms = (_t() - t_begin) * 1000.0
                    top = ", ".join([f"{n}={ms:.1f}ms(len={ln})" for (n, ms, ln) in stage_timings])
                    tag = "PipelineTimeline" if timeline_enabled else "PerfDiag(Pipeline)"
                    self.logger.info(
                        "%s: loop=%d total=%.1fms | %s",
                        tag,
                        self._perf_diag_loop,
                        total_ms,
                        top,
                    )
                except Exception:
                    pass
                self._log_mp_barrier_diag()

        return pipeline_results

    def _log_mp_barrier_diag(self) -> None:
        if not self._perf_diag_env:
            return
        every = max(1, int(self._perf_diag_every or 60))
        if (self._perf_diag_loop % every) != 0:
            return
        estimate_stats = getattr(self, "estimate_mp_backlog_stats", None)
        estimate_legacy = getattr(self, "estimate_mp_pending_depth", None)
        if not callable(estimate_stats) and not callable(estimate_legacy):
            return
        try:
            if callable(estimate_stats):
                stats = estimate_stats()
                pending = int(stats.get("pending", 0))
                put_dropped = int(stats.get("put_dropped", 0))
                pending_evict = int(stats.get("pending_evict", 0))
            else:
                pending, put_dropped = estimate_legacy()
                pending_evict = 0
            self.logger.info(
                "PerfDiag(MpBarrier): pending=%d put_dropped=%d pending_evict=%d",
                pending,
                put_dropped,
                pending_evict,
            )
        except Exception:
            pass

    def calc_memory_consumption(self):
        """Calculate memory consumption for all processors"""
        total = 0
        for processor in self.processors:
            if processor is not None:
                processor.calc_memory_consumption()
                total += processor.get_memory_usage()
        self.memory_measure_results = total

    def get_dropped_ids(self):
        """Get dropped frame IDs from all processors"""
        dropped = []
        for processor in self.processors:
            if processor is not None:
                dropped.extend(processor.get_dropped_ids())
        return dropped

    def insert_debug_info_by_id(self, debug_info: dict):
        """
        Insert debug information from all pipeline processors into debug_info dict.
        
        Args:
            debug_info: Dictionary to store debug information
        """
        for processor in self.processors:
            if processor is not None:
                processor.insert_debug_info_by_id(processor.get_name(), debug_info)

    def get_sources(self):
        """Get video sources for external subscriptions (events, etc.)"""
        return self.sources_proc.get_processors() if self.sources_proc else []

    def run_sources(self):
        """Run source processors"""
        for processor in self.processors:
            if isinstance(processor, ProcessorSource):
                processor.run_sources()
                break

    def get_processor_params(self, processor_name: str) -> List[Dict]:
        """Get parameters for specific processor type"""
        return self._processor_params.get(processor_name, [])

    def set_processor_params(self, processor_name: str, params: List[Dict]):
        """Set parameters for specific processor type"""
        self._processor_params[processor_name] = params

    def get_ipc_mode(self) -> str:
        return self._ipc_mode

    # Protected methods for processor management
    def _add_processor(self, processor: ProcessorBase):
        """Add processor to the pipeline"""
        self.processors.append(processor)

        if isinstance(processor, ProcessorSource):
            self.sources_proc = processor
        self._final_results_name = processor.get_name()

    def generate_default_structure(self, num_sources: int):
        """Generate default structure for pipeline"""
        # Default implementation for processor-based pipelines
        pass
