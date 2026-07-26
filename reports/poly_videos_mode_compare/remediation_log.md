# Исправления в ходе эксперимента (MP FPS)

## Коммиты

| Hash | Описание |
| --- | --- |
| e671955 | Скрипты bench: analyze, e2e, compare, runner |
| c8d6c8c | mp_queue_config, абсолютные пути YOLO, drain env |
| d82b1bc | MpBarrier log, sync_mp, controller backpressure |

## Post-fix bench (2026-05-22)

- Env: `EVILEYE_MP_QUEUE_SCALE=2`, `EVILEYE_MP_DRAIN_POLL_SEC=0.01`
- 20/20 runs OK, 0 tracebacks, 0 drop_events
- MpBarrier: pending 50–75, dropped=0

## Вывод

Увеличение очередей без backpressure снизило controller loop Hz; следующий шаг — bench с `SCALE=1` + drain 0.01 или `SCALE=2` + `EVILEYE_CONTROLLER_BACKPRESSURE=1`.
