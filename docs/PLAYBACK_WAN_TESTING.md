# Playback WAN и cache-диагностика

Руководство по воспроизведению проблем remote-пользователей (медленная загрузка дня, мигание «Ищем кадр…») и проверке гипотезы **«admin видит warm cache, user — cold path»**.

## Переменные окружения

| Переменная | Пример | Назначение |
|------------|--------|------------|
| `EVILEYE_E2E_BASE` | `https://traefik-host/` | URL через Traefik HTTPS (не `127.0.0.1:8181` для WAN-тестов) |
| `EVILEYE_E2E_USER` | `playback-test@local` | Логин test-user |
| `EVILEYE_E2E_PASSWORD` | `…` | Пароль test-user |
| `EVILEYE_E2E_ADMIN_USER` | `admin` | Admin для сценариев C3 |
| `EVILEYE_E2E_ADMIN_PASSWORD` | `…` | Пароль admin |
| `E2E_PLAYBACK_DATE` | `2026-08-19` | Дата с архивом |
| `E2E_PLAYBACK_COLD_DATE` | `2026-01-15` | Дата без прогретого индекса (cold) |
| `E2E_PLAYBACK_CAMERAS` | `Cam1,Cam2` | Камеры test-user |
| `EVILEYE_PLAYBACK_DEBUG` | `1` | Включить `POST /api/v1/playback/_debug/clear-memory-cache` |

Создание test-user:

```bash
python3 scripts/ensure_playback_test_user.py
```

## Матрица кэш-слоёв (cache audit)

| Слой | Файл / ключ | Per-user? | Ключ кэша | TTL | Кто выигрывает от прогрева |
|------|-------------|-----------|-----------|-----|----------------------------|
| SPA in-memory | `evileye/api/frontend/src/api/dataCache.ts` | **Да** (per-browser) | `playback:segments:…`, `playback:detections:…` | 30–90 с | Только тот же браузер |
| Static metadata | `usePlaybackStaticMetadata` module Map | **Да** | camera+date+ts | session | Тот же браузер |
| Server memory | `evileye/api/routes/playback.py` `_memory_cache` | **Нет** | `playback:timeline:{date}:{run_id}:{from}:{to}:{cam_list}` | 45 с | Разный `cam_list` после ACL → разные ключи |
| Detections memory | `_memory_cache` | **Нет** | `playback:detections:scan:{date}:{run_id}:ticks:{cam_list}` | 30 с | То же |
| Cameras memory | `_memory_cache` | **Нет** (до ACL) | `playback:cameras:{run_id}:{date}` | sticky | Общий для всех |
| On-disk segment index | `Streams/{date}/_timeline_segments.json` | **Общий** | по дате | до rebuild | Admin открыл день → user быстрее |
| On-disk detection ticks | `Detections/{date}/Metadata/detection_ticks.json` | **Общий** | по дате | до rebuild | Любой пользователь |
| Background warmer | `playback_index_warmer.py` | **Общий** | detection_ticks | cron | Не все даты |
| Media Range | `/playback/media` | **Нет** | — | — | Не влияет на загрузку дня |

**Вывод:** отдельного server-side кэша на пользователя нет, но admin может маскировать проблему через warm browser cache, общие on-disk индексы и другой набор камер в memory-ключе.

### Response headers (диагностика)

| Header | Значения | Эндпоинты |
|--------|----------|-----------|
| `X-Playback-Cache` | `hit`, `miss`, `stale` | `/playback/timeline`, `/cameras`, `/detections` |

`/ready` дополнительно отдаёт `playback_memory_cache: { keys, fresh, expired, sticky }`.

Cold server simulation (требует `EVILEYE_PLAYBACK_DEBUG=1` + admin cookie):

```bash
curl -X POST -b "$ADMIN_COOKIE" "$BASE/api/v1/playback/_debug/clear-memory-cache"
```

## Сценарии C1–C6

| ID | Подготовка | Кто | Метрики |
|----|------------|-----|---------|
| C1 `cold_server` | restart API или clear memory cache | test-user | timeline p95, `X-Playback-Cache`, mtime индексов |
| C2 `warm_server` | повтор C1 без restart | test-user | ratio C1/C2 |
| C3 `admin_then_user` | admin открывает день D → incognito test-user | user | выигрыш только от disk? |
| C4 `user_alone` | user первый на день D, admin не заходил | user | worst case |
| C5 `cold_date` | архивная дата без `detection_ticks.json` | test-user | time_to_segmentsLoaded |
| C6 `client_cache` | два open подряд vs hard refresh | same user | SPA cache hit |

## Запуск диагностики

### Серверный probe

```bash
export EVILEYE_E2E_BASE=https://traefik-host/
export EVILEYE_E2E_USER=playback-test@local
export EVILEYE_E2E_PASSWORD=...
export E2E_PLAYBACK_DATE=2026-08-19
export E2E_PLAYBACK_CAMERAS=Cam1,Cam2

python3 scripts/diagnose_playback_wan.py --scenario all --output /tmp/wan_probe.json
```

Сценарии: `cold`, `warm`, `admin_then_user`, `user_alone`, `cold_date`.

### E2E (Playwright)

```bash
export EVILEYE_E2E_BASE=https://traefik-host/
npx playwright test tests/e2e/playback_wan_diagnostics.spec.ts
npx playwright test tests/e2e/playback_cache_diagnostics.spec.ts
```

Профили сети: `lan`, `wan_typical`, `wan_bad` (CDP `Network.emulateNetworkConditions`).

### Полный прогон

```bash
./scripts/validate_playback_wan.sh
```

## Baseline-пороги (калибровать на вашем архиве)

| Метрика | lan | wan_typical | wan_bad |
|---------|-----|-------------|---------|
| timeline p95 | < 3 s | < 15 s | < 30 s |
| day_load_total | < 5 s | < 25 s | < 60 s |
| seeking_hint_toggles / 5 seeks | 0–1 | ≤ 2 | ≤ 4 |
| playback 503 count | 0 | 0 | ≤ 2 |
| C1/C2 ratio (memory) | — | > 3× = memory существенен | |
| C3 vs C4 (disk warm) | — | C3 << C4 = admin прогревает disk | |
| C6 ratio (client) | — | > 2× = SPA cache маскирует | |

## Интерпретация cache-гипотезы

| Наблюдение | Интерпретация |
|------------|---------------|
| C1/C2 ratio > 3× | In-memory cache существенно ускоряет повторные запросы |
| C3 << C4 | Admin прогревает on-disk индексы для user |
| C4 ≈ C1 | User реально страдает на cold day |
| C6 ratio > 2× | Browser cache маскирует у частого посетителя |
| `X-Playback-Cache: stale` на cold | UI повторяет запросы → растянутая загрузка |
| Admin fast, user slow на C1 | ACL cam_list или WAN, не per-user server cache |

## Связанные файлы

- `scripts/diagnose_playback_wan.py` — API timings, cache headers, index mtime
- `scripts/ensure_playback_test_user.py` — создание test-user
- `scripts/validate_playback_wan.sh` — orchestration
- `tests/e2e/playback_wan_diagnostics.spec.ts` — day load + seek hint
- `tests/e2e/playback_cache_diagnostics.spec.ts` — C1–C6
- `tests/e2e/helpers/networkProfiles.ts` — CDP network emulation
