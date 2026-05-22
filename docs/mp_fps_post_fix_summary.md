# MP FPS post-fix summary

Заполняется после повторного бенчмарка:

```bash
python scripts/compare_poly_bench_runs.py
```

Baseline: `reports/poly_videos_mode_compare/baseline_pre_fix/`.

**Целевой KPI:** `e2e_tracker_fps` (process) / `e2e_tracker_fps` (thread) ≥ 0.70 для OpenCV.
