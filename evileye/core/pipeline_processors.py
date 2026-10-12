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
            if section_name in {"pipeline_class", "ipc_mode", "modules"}:
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
        """Start frame workers and require readiness before starting sources."""
        import time
        import queue
        from ..object_detector.object_detection_base import ObjectDetectorBase

        frame_workers = []
        for processor in self.processors:
            if processor is None or isinstance(processor, ProcessorSource):
                continue
            for inner in getattr(processor, "processors", ()):
                if isinstance(inner, ObjectDetectorBase) or callable(
                    getattr(inner, "is_ready", None)
                ):
                    frame_workers.append(inner)

        try:
            readiness_timeout = float(
                os.getenv("EVILEYE_FRAME_WORKER_READY_TIMEOUT_SEC", "30.0")
            )
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "EVILEYE_FRAME_WORKER_READY_TIMEOUT_SEC must be a positive number"
            ) from exc
        if readiness_timeout <= 0:
            raise RuntimeError(
                "EVILEYE_FRAME_WORKER_READY_TIMEOUT_SEC must be a positive number"
            )

        for processor in self.processors:
            if processor is not None and not isinstance(processor, ProcessorSource):
                processor.start()

        if frame_workers:
            self.logger.info(
                "Waiting up to %.1fs for %d frame worker(s) to initialize",
                readiness_timeout,
                len(frame_workers),
            )
            ready_results: queue.Queue = queue.Queue()

            def _check_ready(worker):
                try:
                    ready_results.put((worker, bool(worker.is_ready(readiness_timeout)), None))
                except Exception as exc:
                    ready_results.put((worker, False, exc))

            readiness_threads = [
                threading.Thread(
                    target=_check_ready,
                    args=(worker,),
                    name=f"Readiness-{getattr(worker, 'module_id', worker.__class__.__name__)}",
                    daemon=True,
                )
                for worker in frame_workers
                if callable(getattr(worker, "is_ready", None))
            ]
            missing_readiness = [
                worker for worker in frame_workers
                if not callable(getattr(worker, "is_ready", None))
            ]
            for thread in readiness_threads:
                thread.start()

            failed_workers = [
                getattr(worker, "module_id", worker.__class__.__name__)
                for worker in missing_readiness
            ]
            received_workers = set()
            deadline = time.monotonic() + readiness_timeout + 1.0
            for _ in readiness_threads:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    worker, ready, error = ready_results.get(timeout=remaining)
                except queue.Empty:
                    break
                received_workers.add(id(worker))
                name = getattr(worker, "module_id", worker.__class__.__name__)
                if error is not None:
                    self.logger.error("Frame worker %s readiness check failed: %s", name, error)
                if not ready:
                    failed_workers.append(name)

            failed_workers.extend(
                getattr(worker, "module_id", worker.__class__.__name__)
                for worker in frame_workers
                if callable(getattr(worker, "is_ready", None))
                and id(worker) not in received_workers
            )

            if failed_workers:
                failure = RuntimeError(
                    "Frame workers did not become ready; pipeline sources were not started "
                    f"(modules: {', '.join(dict.fromkeys(failed_workers))})"
                )
                self.logger.error("%s", failure)
                try:
                    self.stop()
                except Exception:
                    self.logger.exception("Failed to clean up processors after startup failure")
                raise failure

            self.logger.info("All frame workers are ready")
        else:
            time.sleep(0.1)

        for processor in self.processors:
            if processor is not None and isinstance(processor, ProcessorSource):
                processor.start()

    def stop(self):
        """Stop all processors: GPU stages first, then other stages, capture last."""
        stop_timeout_sec = float(
            os.getenv("EVILEYE_PROCESSOR_STOP_TIMEOUT_SEC", "8.0") or "8.0"
        )
        source_processors = [p for p in self.processors if p is not None and isinstance(p, ProcessorSource)]
        other_processors = [
            p for p in self.processors
            if p is not None and not isinstance(p, ProcessorSource)
        ]
        detector_processors = [
            p for p in other_processors
            if getattr(p, "processor_name", None) == "detectors"
        ]
        non_detector_others = [
            p for p in reversed(other_processors)
            if p not in detector_processors
        ]
        stop_order = [*detector_processors, *non_detector_others, *source_processors]
        for processor in stop_order:
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

    @staticmethod
    def _queue_has_items(value) -> bool | None:
        if value is None:
            return False
        qsize = getattr(value, "qsize", None)
        if not callable(qsize):
            return None
        try:
            return int(qsize()) > 0
        except Exception:
            return None

    def get_pending_work_summary(self) -> list[str]:
        pending = []
        estimate_stats = getattr(self, "estimate_mp_backlog_stats", None)
        if callable(estimate_stats):
            try:
                stats = estimate_stats()
                if int(stats.get("pending", 0)) > 0:
                    pending.append(f"multiprocess={int(stats['pending'])}")
            except Exception:
                pending.append("multiprocess=unknown")

        for container in self.processors or ():
            if container is None:
                continue
            fanout_pending = getattr(container, "_detector_fanout_pending", None)
            if fanout_pending:
                pending.append(f"{container.get_name()}_detector_fanout={len(fanout_pending)}")
            for module in getattr(container, "processors", ()) or ():
                module_id = getattr(module, "module_id", module.__class__.__name__)
                module_pending = False
                has_pending = getattr(module, "has_pending_work", None)
                if callable(has_pending):
                    try:
                        module_pending = bool(has_pending())
                    except Exception:
                        pending.append(f"{module_id}=unknown")
                        continue
                stats_provider = getattr(module, "get_runtime_stats", None)
                if callable(stats_provider):
                    try:
                        stats = stats_provider()
                        module_pending = module_pending or int(
                            stats.get("in_flight", 0) or 0
                        ) > 0
                    except Exception:
                        pending.append(f"{module_id}=unknown")
                        continue
                queue_depth_unknown = False
                for attr in ("queue_in", "queue_out", "_input_queue", "_output_queue"):
                    queue_pending = self._queue_has_items(getattr(module, attr, None))
                    if queue_pending is True:
                        module_pending = True
                        break
                    if queue_pending is None:
                        queue_depth_unknown = True
                if module_pending:
                    pending.append(f"{module_id}=in_flight")
                elif queue_depth_unknown:
                    pending.append(f"{module_id}=queue_depth_unknown")
        return pending

    def has_pending_work(self) -> bool:
        return bool(self.get_pending_work_summary())

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
        debug_info["runtime"] = self.get_runtime_stats()

    def get_runtime_stats(self) -> dict[str, Any]:
        """Aggregate health of generic plugin modules and detector fanout."""
        modules = {}
        stages = {}
        for stage in self.processors:
            if stage is None:
                continue
            for processor in getattr(stage, "processors", []):
                get_stats = getattr(processor, "get_runtime_stats", None)
                if not callable(get_stats):
                    continue
                try:
                    key = f"{stage.get_name()}/{getattr(processor, 'module_id', processor.__class__.__name__)}"
                    modules[key] = get_stats()
                except Exception as exc:
                    modules[f"{stage.get_name()}/{processor.__class__.__name__}"] = {
                        "degraded": True,
                        "diagnostic_error": str(exc),
                    }
            pending_fanout = getattr(stage, "_detector_fanout_pending", None)
            fanout_incomplete = int(getattr(stage, "_detector_fanout_incomplete_count", 0) or 0)
            fanout_dropped = int(getattr(stage, "_detector_fanout_dropped_count", 0) or 0)
            if pending_fanout or fanout_incomplete or fanout_dropped:
                stage_name = stage.get_name()
                stages[stage_name] = {
                    "degraded": fanout_incomplete > 0,
                    "detector_fanout_policy": getattr(stage, "detector_fanout_policy", "forward_partial"),
                    "pending_detector_fanout": len(pending_fanout or {}),
                    "detector_fanout_incomplete": fanout_incomplete,
                    "detector_fanout_dropped": fanout_dropped,
                }
        return {
            "degraded": any(bool(stats.get("degraded")) for stats in modules.values())
            or any(bool(stats.get("degraded")) for stats in stages.values()),
            "modules": modules,
            "stages": stages,
        }

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
