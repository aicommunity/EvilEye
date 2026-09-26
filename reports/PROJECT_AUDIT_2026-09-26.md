# Аудит проекта EvilEye — 2026-09-26

Метод: docs/reports + статическая верификация `evileye/` + remediation по плану.  
Предыдущие аудиты: [PROJECT_AUDIT_2026-09-23.md](PROJECT_AUDIT_2026-09-23.md), [PROJECT_REAUDIT_32acaa52.md](PROJECT_REAUDIT_32acaa52.md), [AUDIT_FOLLOWUP_dcfc98dd.md](AUDIT_FOLLOWUP_dcfc98dd.md).

## Вердикт

Веб-P0 ACL из сентябрьских аудитов в основном закрыты ранее. В этом цикле закрыты:

- **C1/C2** — рассинхрон FIFO `MpAsyncBridge` / restart без drain
- **H1–H4** — пустые кадры SHM, Cam-2 ACL, атрибуты без `source_id`, owners медиа
- **RAM waste** — ROI/attrs IPC, GUI clone, zone JPEG sticky, EventBuffer byte budget, config guards
- **DX** — event registry, per-item `type`, `PipelineDeclarative`, DualMode reference (RoiFeeder), examples

## Архитектура (кратко)

```
Config JSON → Controller → Pipeline (Surveillance | Declarative)
  → Capture SHM → Detector (MpAsyncBridge) → Tracker → ObjectsHandler
  → Event registry → DB/JSON adapters → GUI / FrameBroker / Web
```

## 1. Корректность — статус

| ID | Было | Сделано |
|----|------|---------|
| **C1** | Cap-evict release SHM без удаления из `input_queue` | [mp_async_bridge.py](../evileye/core/mp_async_bridge.py): queue drop + pairing index; тесты parity |
| **C2** | Restart без drain | [mp_control.py](../evileye/core/mp_control.py) `drain_ipc_queues` + `on_before_worker_restart`; det/track clear bridge |
| **H1** | `consume_frame` → `np.array([])` | возвращает `None`; callers отбрасывают empty |
| **H2** | `Cam-2` дробился на `Cam`/`2` | `_split_stream_folder` → `[folder]` если не composite |
| **H3** | AttributeManager только `track_id` | ключ `(source_id, track_id)` |
| **H4** | Owners через эвристики Events→Detections | sidecar `.owner` + filename parse + Events metadata |

Закрытые ранее (не повторяли): A01–A05, F01/F03/F04/F05/F07/F08, R03/R04/R06.

Остаётся (не блокер этого цикла): F09–F11 playback coverage/admission/budget, F12 полный CI gate, F13 perf proof, TD-DB-BATCH / TD-GUI-SPLIT.

## 2. Память

### Исправлено (waste)

| # | Изменение |
|---|-----------|
| A2 | RoiFeeder: `process` → thread (bbox-only) |
| A3 | AttributeClassifier MP: IPC только ROI crops |
| A4 | GUI: `clone_capture_image` перед overlay |
| A5 | Zone sticky: JPEG lazy decode; clear на exit |
| A6 | `last_image` clear после lost persist |
| A7 | preview resize без лишнего `.copy()` |
| C3/C4 | `validate_config` warns `num_detection_threads>1`; EventBuffer `EVILEYE_EVENT_BUFFER_MAX_MB` |

### Intentional (оставить)

YOLO per process, SHM det/track, pending caps, EventBuffer maxlen, FrameBroker latest-JPEG.

## 3. Архитектура / DX

| Было | Стало |
|------|-------|
| Homogeneous `params[0].type` | Per-item `class_names` в ProcessorSource/Frame/Step |
| Events hardcoded в EventsService | [event_registry.py](../evileye/events_detectors/event_registry.py) + `events_detectors.enabled` |
| Нет declarative stages | [PipelineDeclarative](../evileye/pipelines/pipeline_declarative.py) |
| DualMode skeleton | Base hooks + RoiFeeder adoption |
| Почти нет examples | [custom_pipeline_stage](../examples/custom_pipeline_stage/), [custom_event_detector](../examples/custom_event_detector/) |
| Docs опережали код | Touch matrix в [PIPELINE_ARCHITECTURE.md](../docs/PIPELINE_ARCHITECTURE.md); DI уже помечен roadmap |

## 4. Тесты

- `tests/unit/core/test_mp_async_bridge.py` — FIFO/cap/overflow parity
- `tests/unit/core/test_frame_transport_ipc.py` — missing SHM → None
- `tests/unit/api/test_reaudit_media_acl.py` — Cam-2, detection owners
- `tests/unit/objects_handler/test_attribute_manager_source_id.py`
- `tests/unit/core/test_plugin_dx_audit.py` — per-item types + registry

## 5. Рекомендации дальше

1. Playback F09–F11 (coverage / admission / process-wide cache budget).
2. DualMode adoption для YOLO detector (полный S1).
3. Optional: RuntimeHost без PyQt imports.
4. Soak KPI после RAM-правок (`soak_mp_memory` / poly-videos).
