# Каталог результатов benchmark

Манифест матрицы: `reports/linux_perf_matrix_mp_per_camera/configs/matrix_manifest.json`

## Содержимое

- `summary.csv`, `speedup.csv`, `report.md` — сводка по всей матрице.
- `summary_plots/` — графики ускорения из сводного renderer-а (если построены).
- `tables/*_results.csv` — таблицы по каждой группе (устройство × сценарий × layout).
- `plots/<группа>/` — графики FPS и ресурсов для группы.

## Группы в этой итерации

- `GPU` / `захват + обнаружение + отслеживание` / `захват, обнаружение и отслеживание в отдельных процессах (по одному процессу на камеру)` → `reports/linux_perf_matrix_mp_per_camera/results/cuda_0/tracking/process_full`
- `GPU` / `полный пайплайн` / `захват, обнаружение и отслеживание в отдельных процессах (по одному процессу на камеру)` → `reports/linux_perf_matrix_mp_per_camera/results/cuda_0/full/process_full`
- `CPU` / `захват + обнаружение + отслеживание` / `захват, обнаружение и отслеживание в отдельных процессах (по одному процессу на камеру)` → `reports/linux_perf_matrix_mp_per_camera/results/cpu/tracking/process_full`
- `CPU` / `полный пайплайн` / `захват, обнаружение и отслеживание в отдельных процессах (по одному процессу на камеру)` → `reports/linux_perf_matrix_mp_per_camera/results/cpu/full/process_full`

Скопировано файлов графиков: 32.

Подробная методика: `docs/diploma_benchmark_methodology.md`.
