"""Measure per-item plugin runtime overhead without model inference.

Run in an EvilEye environment with a lightweight ``processor_item`` plugin
installed. The plugin must accept and return ``(payload, Frame)`` and may declare
``accepts_frame_handle`` to exercise shared-frame transport in process mode.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from evileye.core.base_class import EvilEyeBase
from evileye.core.frame import Frame
from evileye.core.plugins import plugin_manager, plugin_registry


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * percentile)))
    return ordered[index]


def _summary(latencies_ms: list[float]) -> dict[str, float]:
    elapsed_sec = sum(latencies_ms) / 1000.0
    return {
        "items": len(latencies_ms),
        "throughput_items_sec": len(latencies_ms) / elapsed_sec,
        "latency_p50_ms": statistics.median(latencies_ms),
        "latency_p95_ms": _percentile(latencies_ms, 0.95),
        "latency_max_ms": max(latencies_ms),
    }


def _frame(index: int, width: int, height: int) -> Frame:
    frame = Frame()
    frame.source_id = 0
    frame.frame_id = index
    frame.frame_version = 1
    frame.time_stamp = time.time()
    frame.image = np.zeros((height, width, 3), dtype=np.uint8)
    return frame


def _measure_direct(registered, config, warmup, count, width, height):
    module = registered.spec.factory(config)
    state_factory = getattr(module, "create_state", None)
    state = state_factory(config) if callable(state_factory) else None

    def run(index):
        item = ({}, _frame(index, width, height))
        return item, module.process_item(item, state)

    def validate(result):
        if not isinstance(result, (list, tuple)) or result[0].get("plugin_label") != config["label"]:
            raise AssertionError(f"unexpected direct output: {result!r}")

    for index in range(warmup):
        _, result = run(index)
        validate(result)
    samples = []
    for index in range(count):
        item = ({}, _frame(warmup + index, width, height))
        started = time.perf_counter_ns()
        result = module.process_item(item, state)
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
        validate(result)
    close = getattr(state, "close", None)
    if callable(close):
        close()
    return _summary(samples)


def _measure_runtime(module_id, config, mode, warmup, count, width, height):
    adapter = EvilEyeBase.create_instance(module_id)
    adapter.set_params(
        module_id=module_id,
        execution_mode=mode,
        source_ids=[0],
        queue_size=8,
        config=config,
    )
    if not adapter.init():
        raise RuntimeError(f"{module_id} failed to initialize for {mode}")
    adapter.start()
    if not adapter.is_ready(20):
        adapter.stop()
        adapter.release()
        raise RuntimeError(f"{module_id} worker did not become ready in {mode}")

    def measure_one(index):
        item = ({}, _frame(index, width, height))
        started = time.perf_counter_ns()
        adapter.put(item)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            result = adapter.get()
            if result is not None:
                elapsed = (time.perf_counter_ns() - started) / 1_000_000
                if result[0].get("plugin_label") != config["label"]:
                    raise AssertionError(f"unexpected {mode} output: {result!r}")
                if result[1].image is None or result[1].image.shape != (height, width, 3):
                    raise AssertionError(f"{mode} did not restore the original frame")
                if result[1].frame_version != 1:
                    raise AssertionError(f"{mode} did not preserve frame metadata")
                return elapsed
            time.sleep(0.0005)
        raise TimeoutError(f"{module_id} did not return item {index} in {mode}")

    try:
        for index in range(warmup):
            measure_one(index)
        samples = [measure_one(warmup + index) for index in range(count)]
        return _summary(samples)
    finally:
        adapter.stop()
        adapter.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module-id", default="example/add-label")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.count < 1 or args.warmup < 0 or args.width < 1 or args.height < 1:
        parser.error("count/size must be positive and warmup must be non-negative")

    plugin_manager.load()
    registered = plugin_registry.get_module(args.module_id)
    if registered is None or registered.spec.kind != "processor_item":
        raise SystemExit(f"not a discovered processor_item plugin: {args.module_id}")
    if not {"thread", "process"}.issubset(registered.spec.execution_modes):
        raise SystemExit("benchmark plugin must support both thread and process")
    config = {"label": "runtime-benchmark"}
    result = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "module_id": args.module_id,
        "python": __import__("sys").version.split()[0],
        "frame_size": {"width": args.width, "height": args.height, "channels": 3},
        "warmup": args.warmup,
        "measurement_count": args.count,
        "capabilities": sorted(registered.spec.capabilities),
        "method": "single-item round-trip; no model inference; frame payload restored by runtime",
        "modes": {
            "direct_call": _measure_direct(
                registered, config, args.warmup, args.count, args.width, args.height
            ),
            "thread": _measure_runtime(
                args.module_id, config, "thread", args.warmup, args.count, args.width, args.height
            ),
            "process": _measure_runtime(
                args.module_id, config, "process", args.warmup, args.count, args.width, args.height
            ),
        },
    }
    encoded = json.dumps(result, indent=2, sort_keys=True)
    print(encoded)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
