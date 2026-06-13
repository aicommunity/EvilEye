# Scope merge: ветка `benchmarks` → `main`

Рекомендации по интеграции ветки `benchmarks` в `main` (2026-06-13).

## Объём изменений

| Категория | Файлов (ориентир) | Рекомендация |
|-----------|-------------------|--------------|
| Код `evileye/` | ~200+ | **Merge обязательно** — MP refactor R0–R6, process default |
| `scripts/` benchmark | ~25 | **Merge** — tooling + runbook |
| `tests/` unit/integration | ~80 новых/изменённых | **Merge** — контракты MP |
| `docs/` | ~15 | **Merge** — включая [diploma_benchmark_methodology.md](diploma_benchmark_methodology.md) |
| `configs/` poly/thread/mp пары | ~30 | **Merge** — нужны для bench и gate |
| `reports/` артефакты прогонов | ~1000 | **Не merge** (или LFS / отдельная ветка docs-only) |

**Diff vs `main`:** ~166 коммитов, ~1567 файлов, +161k / −15k строк.

## Рекомендуемая стратегия

### Вариант A (предпочтительный): два PR

1. **PR-1 `benchmarks-core`** — код + tests + scripts + docs + configs  
   - Без `reports/linux_perf_matrix_mp_per_camera/results/**`  
   - Без `reports/poly_videos_mode_compare/**/logs`, `samples`  
   - Оставить только summary/gate markdown: `reports/mp_refactor_gate/*.md`, `diploma_report/` summary CSV (опционально)

2. **PR-2 `benchmarks-artifacts`** (optional) — тяжёлые CSV/logs/plots через Git LFS или внешнее хранилище

### Вариант B: один PR с `.gitignore` для артефактов

Добавить в `.gitignore`:

```
reports/linux_perf_matrix_mp_per_camera/results/
reports/linux_perf_matrix_mp_per_camera/configs/
reports/poly_videos_mode_compare/**/logs/
reports/poly_videos_mode_compare/**/samples/
```

Оставить в репозитории: `summary/`, `diploma_report/` (без raw logs), `mp_refactor_gate/`.

## Pre-merge checklist

- [ ] Полный E2E gate 90 s + soak 30 min ([diploma_benchmark_methodology.md §5](diploma_benchmark_methodology.md))
- [x] Unit tests MP + benchmark scripts (2026-06-13 PASS)
- [x] IPC KPI gate (2026-06-13 PASS)
- [ ] Review конфликтов с `main` в `evileye/controller/`, `pipelines/`
- [ ] CI pytest на GitHub Actions (если есть)

## Что не блокирует merge

- Исторические отчёты в `reports/*.md` (ROI, Journal) — справочные
- Open TECH_DEBT: TD-MP-401, TD-DOC-001/002
- `DualModeProcessor` skeleton (S1)

## Зависимости runtime

- Default `execution_mode=process` — **breaking change** для деплоев, ожидавших thread; документировать в release notes
- Env F2 defaults уже в коде; явный export не обязателен
