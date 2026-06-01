# GUI Safe30 Performance Report

## Scope

- Duration: 30 seconds per run (`timeout -k 8s 30s`)
- Mode: GUI (`--autoclose`)
- Perf diagnostics: `EVILEYE_PERF_DIAG=1`, `EVILEYE_PERF_DIAG_EVERY=15`
- Date: 2026-04-15

## Executed Matrix

1. `configs/poly-videos.json` -> `logs/diagnostics/poly-videos_baseline_gui_safe30_30s.log` (completed)
2. `configs/poly-videos_mp_safe30.json` -> `logs/diagnostics/poly-videos_mp_safe30_gui_30s.log` (completed)
3. `configs/poly-videos-gst.json` -> `logs/diagnostics/poly-videos-gst_baseline_gui_safe30_30s.log` (killed by OOM, shell exit 137)
4. `configs/poly-videos-gst_mp_safe30.json` -> `logs/diagnostics/poly-videos-gst_mp_safe30_gui_30s.log` (completed)

All completed runs finished without lingering `evileye` processes after shutdown.

## KPI Comparison: poly-videos (Baseline vs MP safe30)

Report: `reports/poly-videos_gui_safe30_30s_kpi.md`

- Warnings/Errors/Tracebacks: unchanged (`4/0/0` vs `4/0/0`)
- Stop timeouts / force-kills / restarts: `0`
- `p95 Pipeline`: `46.7 ms` -> `48.3 ms` (MP safe30 is slower by `+1.6 ms`)
- Estimated pipeline frequency: `21.41 Hz` -> `20.70 Hz`
- Max RSS: `15.77 MB` -> `16.32 MB` (near-equal)
- KPI gate: `PASS`

## KPI Comparison: poly-videos-gst (Baseline vs MP safe30)

Report: `reports/poly-videos-gst_gui_safe30_30s_kpi.md`

- Baseline GUI run was killed by system (`exit 137`) before stable completion.
- MP safe30 run completed, but produced `pipeline_samples=0` in this specific run.
- Gate status: `FAIL` (reason: insufficient pipeline samples).
- Max RSS in logs: baseline `221.35 MB` vs MP safe30 `17.21 MB` (not directly comparable due to baseline OOM and candidate sample gap).

## Stability Findings

- The previous "process explosion" symptom is not observed in safe30 runs.
- Safe30 MP configs keep process count low and avoid orphaned workers post-run.
- The unstable point remains `poly-videos-gst` baseline GUI under current machine memory pressure.

## Recommendations

1. Keep using `*_mp_safe30.json` for GUI stress checks on this host.
2. For `poly-videos-gst` GUI benchmarking, either:
   - run baseline in `--no-gui`, or
   - lower runtime to `15-20s` and disable optional GUI-heavy features during benchmark.
3. For final apples-to-apples GUI KPI on GST pair, run on a host with larger RAM headroom.
