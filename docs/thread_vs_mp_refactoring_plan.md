# План рефакторинга: thread vs MP

Дорожная карта по результатам [аудита контрактов](thread_vs_mp_contracts.md). **Код в этом документе не меняется** — только задачи, порядок PR и критерии приёмки.

---

## §B1. Цели и non-goals

### Цели

- Сократить дублирование **DUP-006**, **DUP-004**, **DUP-007** (MP async, YOLO, BoT-SORT).
- Убрать **COUP-002** (`isinstance(DetectionThreadYoloMp)` в backlog).
- Сохранить KPI фазы 3: `e2e_ratio ≥ 3`, `staleness_in_band`, `drop_events = 0` ([mp_fps_phase3_summary.md](mp_fps_phase3_summary.md)).

### Non-goals

- MC-tracker в subprocess.
- End-to-end descriptor pipeline без materialize в `ProcessorStep`.
- Смена default `execution_mode` с `process` на `thread`.
- Объединение capture + detector в один worker.
- Выполнение R4 (capture triple-buffer) без отдельного spike, если риск регрессии высокий.

---

## §B2. Принципы

1. **Stable facade** — сигнатуры `ObjectDetectorBase.put/get`, `ObjectTrackingBase.put/get`, `VideoCaptureBase.get` не ломать.
2. **Algorithm core** — чистые функции без `Queue` / `MpControl` (тестируемые unit-тестами).
3. **Protocol over isinstance** — `MpPendingReporter` вместо проверки конкретных классов в pipeline.
4. **Incremental PR** — каждая фаза Ri зелёный pytest + smoke bench.
5. **Bench gate** — перед merge R2/R3: сравнение process/thread smoke на poly-videos.

---

## §B3. Фазы R0–R6

### R0 — Documentation & deprecation (~2 SP, 1 PR)

| Task | Действие | Файлы |
|------|----------|-------|
| R0-T1 | Deprecation в docstring `ObjectDetectorYoloMp` | `object_detection_yolo_mp.py` |
| R0-T2 | MULTIPROCESSING: primary = `ObjectDetectorYolo` + `execution_mode` | `docs/MULTIPROCESSING.md` |
| R0-T3 | Warning при factory `"yolo_mp"` / class name legacy | `detection_thread_factory.py` |
| R0-T4 | Без удаления класса | — |

**Закрывает:** DUP-018, частично COUP-012.

**Verify:**

```bash
grep -r "ObjectDetectorYoloMp" configs/ || true
pytest tests/unit/object_detector/ -q
```

---

### R1 — `MpAsyncBridge` (~8 SP, 2 PR)

**Новый модуль (целевой):** `evileye/core/mp_async_bridge.py`

**Черновик API:**

```python
class MpAsyncBridge(Generic[JobT, ResultT]):
    def __init__(
        self,
        *,
        mp_control: MpControl,
        pending_cap: int,
        drain_poll_sec: Callable[[], float],
        name: str,
    ): ...

    def enqueue(self, job: JobT, *, meta: Any) -> tuple[bool, int | None]:
        """Returns (accepted, dropped_frame_id)."""

    def pending_depth(self) -> int: ...
    def diag_stats(self) -> dict[str, int]: ...  # put_dropped, pending_evict

    def start_feed(self, feed_fn: Callable[[], None]) -> None: ...
    def start_drain(self, drain_fn: Callable[[], None]) -> None: ...
    def stop(self, timeout: float) -> None: ...
```

| Task | Действие |
|------|----------|
| R1-T1 | Extract: `_enforce_pending_cap`, `_clear_mp_pending`, enqueue+drop из detector |
| R1-T2 | Подключить `DetectionThreadYoloMp`; parity tests |
| R1-T3 | Подключить `ObjectTrackingBase` process path |
| R1-T4 | Unit: FIFO, cap evict, `put_nowait` drop |

**Закрывает:** DUP-006, DUP-012, DUP-013, DUP-014, DUP-015 (частично), DUP-008 (частично).

**Verify:**

```bash
pytest tests/unit/object_detector/test_detection_thread_yolo_mp_async.py -q
pytest tests/unit/core/test_mp_pending_cap.py -q
```

---

### R2 — Algorithm cores (~13 SP, 3 PR)

| Task | Модуль | Содержимое |
|------|--------|------------|
| R2-T1 | `object_detector/detection_preprocess.py` | `split_rois_for_frame`, stride — общий для feed и `_process_impl` |
| R2-T2 | `object_detector/yolo_runtime.py` | `load_model`, `predict_images`, `predict_handles` |
| R2-T3 | `object_tracker/track_update_core.py` | `update_tracks(...) -> TrackingResultList` |
| R2-T4 | `MpWorkerYolo` → только `yolo_runtime` | |
| R2-T5 | `DetectionThreadYolo._process_impl` → preprocess + runtime | |
| R2-T6 | `MpWorkerTracker` + `ObjectTrackingBotsort` → `track_update_core` | |

**Закрывает:** DUP-003, DUP-004, DUP-005, DUP-007, DUP-009.

**Verify:**

```bash
pytest tests/unit/object_detector/ tests/unit/object_tracker/ -q
export EVILEYE_CONTROLLER_BACKPRESSURE=soft
python scripts/measure_poly_e2e_fps.py \
  --config configs/poly-videos.json \
  --warmup-sec 10 --active-sec 30 --env-note r2_smoke \
  --out /tmp/e2e_r2_smoke.json
# Ожидание: staleness_in_band, e2e_ratio >= 3.0
```

---

### R3 — `MpPendingReporter` (~5 SP, 1 PR)

```python
# evileye/core/mp_pending_protocol.py
from typing import Protocol

class MpPendingReporter(Protocol):
    def mp_pending_depth(self) -> int: ...
    def mp_diag_put_dropped(self) -> int: ...
    def mp_diag_pending_evict(self) -> int: ...
```

| Task | Действие |
|------|----------|
| R3-T1 | Реализовать на `DetectionThreadYoloMp` и process-path `ObjectTrackingBase` |
| R3-T2 | `estimate_mp_backlog_stats` — обход reporters через registry / duck typing |
| R3-T3 | Удалить `isinstance(DetectionThreadYoloMp)` |

**Закрывает:** COUP-002.

**Зависимость:** после R1-T2 (стабильный pending API).

---

### R4 — Capture simplification (~8 SP, 1 PR, optional)

| Task | Действие |
|------|----------|
| R4-T1 | `evileye/capture/queue_policy.py` — `drop_oldest_put(queue)` |
| R4-T2 | Использовать в `DropOldestQueue` и `mp_worker_capture` |
| R4-T3 | Spike: можно ли убрать один уровень буфера (только doc, если риск) |
| R4-T4 | Выровнять GStreamer `start()` ветки |

**Закрывает:** DUP-001, DUP-002. **COUP-001** частично.

**Verify:** integration capture tests, 1× poly process run.

---

### R5 — ProcessorStep cleanup (~5 SP, 1 PR)

| Task | Действие |
|------|----------|
| R5-T1 | `evileye/core/stage_result_normalizer.py` — общий `normalize_stage_result` |
| R5-T2 | Использовать в `ProcessorStep` и `ProcessorFrame` |
| R5-T3 | Документировать drain policy (post-only); optional env object |

**Закрывает:** DUP-010.

---

### R6 — Tracker encoder & parent init (~5 SP, 1 PR)

| Task | Действие |
|------|----------|
| R6-T1 | `ObjectTrackingBotsort.init_impl`: не создавать `BOTSORT` при `execution_mode==process` |
| R6-T2 | Таблица «где грузится OnnxEncoder» в MULTIPROCESSING или architecture doc |
| R6-T3 | Unit: parent без тяжёлого onnx при process |

**Закрывает:** COUP-004, COUP-007.

---

## §B4. Порядок PR

```text
R0 → R1-T1 → R1-T2 → R1-T3 → R3 → R2-T1..T6 → R6 → R5 → R4 (optional)
```

**Нельзя параллелить:** R3 до R1-T2; R2-T4 до R2-T2.

---

## §B5. Критерии приёмки (глобальные)

| KPI | Команда | PASS |
|-----|---------|------|
| Unit core/det/track | `pytest tests/unit/core/ tests/unit/object_detector/ tests/unit/object_tracker/ -q` | 0 failures |
| MP async | `test_detection_thread_yolo_mp_async.py`, `test_sync_mp_adaptive.py` | pass |
| E2E process | `measure_poly_e2e_fps.py` 90s active, `poly-videos.json` | `staleness_in_band`, `e2e_ratio ≥ 3` |
| Drops | `analyze_poly_mp_barriers.py` на matrix smoke | `drop_events == 0` |
| Thread smoke | `run_poly_videos_mode_compare.py` thread config 1 run | no crash |

---

## §B6. Риск-регистр

| Риск | Вероятность | Mitigation |
|------|-------------|------------|
| R2 меняет MP timing / e2e | med | smoke e2e before/after; keep F2 env defaults |
| R1 race в drain | low | сохранить `_mp_pending_lock` в bridge |
| R4 capture regression | med | integration tests only; optional phase |
| Legacy configs с `YoloMp` | low | R0 warnings |
| Регрессия staleness | med | band check в smoke JSON |

---

## §B7. Mapping DUP → R (сводка)

| DUP | R |
|-----|---|
| 001–002 | R4 |
| 003–005, 007, 009 | R2 |
| 006, 008, 012–015 | R1 |
| 010 | R5 |
| 011, 018 | R0 |
| 016 | post-R2 |
| 017 | doc only |

| COUP | R / S |
|------|-------|
| 002 | R3 |
| 004, 007 | R6 |
| 001 | R4 |
| 005 | S6 (doc) |
| 008 | S4 (отложить) |

---

## §B8. Оценка трудозатрат (суммарно)

| Фаза | SP (ориентир) |
|------|---------------|
| R0 | 2 |
| R1 | 8 |
| R2 | 13 |
| R3 | 5 |
| R4 | 8 (optional) |
| R5 | 5 |
| R6 | 5 |
| **Итого core** | **~38 SP** |
| **+ R4** | **~46 SP** |

---

## Связанные документы

- [Аудит контрактов](thread_vs_mp_contracts.md)
- [Гайд разработчика](developing_dual_mode_modules.md)
- [Упрощение интеграции](module_integration_simplification.md)
