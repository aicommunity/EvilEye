# Упрощение интеграции новых модулей (thread / MP)

Предложения по снижению порога входа при добавлении стадий pipeline. Это **design options**, не обязательства репозитория. Зависимости от [плана рефакторинга](thread_vs_mp_refactoring_plan.md).

**Контекст проблемы:** сегодня новый MP-модуль требует ~200 LOC boilerplate (feed/drain, pending, cap, diag), знание SHM, отдельные worker-файлы и согласование с `ProcessorStep` без pre-drain.

---

## §D1. Сводная таблица предложений

| ID | Название | SP | Зависит от | Рекомендация v1 |
|----|----------|-----|------------|-----------------|
| S1 | `DualModeProcessor` base | 8 | R1 | После R1 |
| S2 | `MpPendingReporter` Protocol | 5 | R3 | Вместе с R3 |
| S3 | `AlgorithmCore` callable | 13 | R2 | Core det+track |
| S4 | `module_capabilities` в JSON | 8 | R5 | Отложить |
| S5 | `create_execution_backend()` | 5 | S1 | Опционально |
| S6 | `stage_kind: sync_batch` | 5 | doc | Документ + validator |
| S7 | Config overlay profiles | 3 | — | Bench scripts |

---

## §D2. S1 — `DualModeProcessor`

### Проблема

Дублируется инициализация queues, `start`/`stop`, выбор thread vs process, подъём feed/drain threads (**DUP-006**).

### API sketch

```python
# evileye/core/dual_mode_processor.py (целевой)
class DualModeProcessor(EvilEyeBase):
    execution_mode: str
    queue_in: Queue
    queue_out: Queue

    def init_impl(self, **kwargs):
        if self.execution_mode == EXEC_MODE_PROCESS:
            return self._init_mp(self._worker_class, self._bridge_factory)
        return self._init_thread(self._thread_target)

    # hooks:
    def process_frame_thread(self, item): ...
    def pack_job_for_worker(self, item): ...
    def unpack_worker_result(self, raw): ...
```

### Затрагиваемые файлы

- Новый: `evileye/core/dual_mode_processor.py`
- Миграция: `detection_thread_yolo_mp.py`, `object_tracking_base.py` (постепенно)

### Плюсы / минусы

| + | − |
|---|---|
| Меньше copy-paste | Наследование может скрыть edge cases capture |
| Единый stop/join | Рефакторинг больших классов |

### Рекомендация

**Делать после R1** — когда `MpAsyncBridge` стабилизирован. **Не** использовать для capture (отдельный continuous producer pattern).

---

## §D3. S2 — `MpPendingReporter`

### Проблема

**COUP-002:** pipeline знает `DetectionThreadYoloMp` для backlog.

### API sketch

```python
class MpPendingReporter(Protocol):
    def mp_pending_depth(self) -> int: ...
    def mp_diag_put_dropped(self) -> int: ...
    def mp_diag_pending_evict(self) -> int: ...
```

Регистрация: detector threads + trackers implement; `estimate_mp_backlog_stats` суммирует без `isinstance`.

### SP: 5 | Зависит: **R3**

### Рекомендация

**Делать в v1 вместе с R3** — обязательный шаг для новых MP-модулей (см. [developing_dual_mode_modules.md](developing_dual_mode_modules.md) checklist §10).

---

## §D4. S3 — `AlgorithmCore`

### Проблема

**DUP-004, DUP-007:** один и тот же алгоритм в parent thread и в `MpWorker*`.

### API sketch

```python
# detection
def run_yolo_on_rois(runtime: YoloRuntime, rois: list[Frame]) -> DetectionResultList: ...

# tracking
def update_tracks(state: TrackerState, frame: Frame, dets: DetectionResultList) -> TrackingResultList: ...
```

Thread path: вызывает core в `_process_impl`. Process path: только `worker_impl` → core.

### SP: 13 | Зависит: **R2**

### Рекомендация

**Делать в v1 для det+track** — highest ROI. Attributes (**DUP-016**) — второй эшелон.

---

## §D5. S4 — Declarative `module_capabilities`

### Проблема

Разработчик должен помнить флаги `requires_materialized_frame` / `accepts_frame_handle` и поведение `_adapt_input_for_processor`.

### API sketch

```json
{
  "class_name": "MyPreprocessor",
  "execution_mode": "thread",
  "capabilities": {
    "accepts_frame_handle": true,
    "heavy_compute": false
  }
}
```

`ProcessorStep` читает capabilities из params[0] и решает materialize.

### SP: 8 | Зависит: R5

### Рекомендация

**Отложить** — churn конфигов и CONFIGURATION_GUIDE; пока достаточно явных атрибутов класса.

---

## §D6. S5 — `create_execution_backend(mode, params)`

### Проблема

Разветвлённый `init_impl` в каждом модуле (**COUP-012**, **DUP-011**).

### API sketch

```python
def create_execution_backend(
    mode: str,
    *,
    thread_factory: Callable[[], ThreadBackend],
    process_factory: Callable[[], ProcessBackend],
) -> ExecutionBackend: ...
```

### SP: 5 | Зависит: S1

### Рекомендация

**Опционально** — тонкая обёртка после S1; не блокирует новые модули.

---

## §D7. S6 — `stage_kind: sync_batch`

### Проблема

**COUP-005:** MC использует hardcoded `processor_name` и `isinstance`; новые batch-стадии копируют паттерн ad hoc.

### API sketch

```json
{
  "class_name": "ObjectMultiCameraTracking",
  "stage_kind": "sync_batch"
}
```

Pipeline: validator предупреждает, если задан `execution_mode` на sync stage. `ProcessorStep` dispatch по `stage_kind`.

### SP: 5

### Рекомендация

**v1: документ + warning в config validator** (без большого рефакторинга step). Полный dispatch по kind — v2.

---

## §D8. S7 — Config overlay profiles

### Проблема

Два полных JSON (`poly-videos` / `poly-videos-thread`) — 13 отличий только в `execution_mode`.

### API sketch

```json
{
  "pipeline": { "...": "base" },
  "profiles": {
    "process": {},
    "thread": {
      "pipeline.sources[*].execution_mode": "thread"
    }
  }
}
```

Bench loader merges profile (скрипт, не runtime).

### SP: 3 | Независимо

### Рекомендация

**Делать для bench/scripts** — не менять `evileye run` без ADR. Упрощает сравнение, не упрощает runtime integration.

---

## §D9. Roadmap упрощения

| Этап | Deliverable | Упрощает |
|------|-------------|----------|
| Docs (текущий) | contracts + dev-guide | Понимание |
| R0–R1 | MpAsyncBridge | S1 |
| R2–R3 | Algorithm core + Reporter | S2, S3 |
| R5–R6 | normalize + encoder | S4 prep |
| v2 | DualModeProcessor + stage_kind | S1, S6 |
| Bench | overlay profiles | S7 |

---

## §D10. ADR-заготовки (только заголовки)

| ADR | Тезис |
|-----|-------|
| ADR-001 | Default `execution_mode` остаётся `process` |
| ADR-002 | Facade queues остаются `threading.Queue` в parent |
| ADR-003 | MC и аналоги — sync-only, без MP |
| ADR-004 | Новые MP-модули после R1 обязаны использовать shared async bridge |
| ADR-005 | AlgorithmCore обязателен для новых heavy stages post-R2 |

Полные ADR-файлы — по запросу команды, вне текущего scope.

---

## §D11. Минимальный путь для нового модуля «сегодня»

Без ожидания S1–S7:

1. Скопировать структуру **шаблона A** из [developing_dual_mode_modules.md](developing_dual_mode_modules.md).
2. Зарегистрировать `@EvilEyeBase.register`.
3. Пройти **чеклист 20 пунктов**.
4. Не добавлять `isinstance` в `pipeline_surveillance`.
5. После merge R3 — реализовать `MpPendingReporter`.

---

## Связанные документы

- [thread_vs_mp_contracts.md](thread_vs_mp_contracts.md)
- [thread_vs_mp_refactoring_plan.md](thread_vs_mp_refactoring_plan.md)
- [developing_dual_mode_modules.md](developing_dual_mode_modules.md)
