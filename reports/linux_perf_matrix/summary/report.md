# Сводный отчет по Linux benchmark

## Артефакты
- `summary.csv` — все строки измерений с CPU, GPU и RAM.
- `speedup.csv` — парные ускорения `process/thread` по основной метрике сценария.
- `plots/` — графики ускорения по числу камер.

## Контроль валидности
Прогоны помечаются непригодными для итогового вывода, если были ошибки, traceback, timeout или превышены заданные пороги CPU/GPU/RAM.

## Лучшие валидные ускорения
| Устройство | Сценарий | Схема multiprocessing | Камер | Ускорение |
| --- | --- | --- | ---: | ---: |
| CPU | полный пайплайн | в отдельном процессе только обнаружение | 4 | 171,27 |
| CPU | полный пайплайн | в отдельном процессе только обнаружение | 3 | 163,10 |
| CPU | захват + обнаружение + отслеживание | в отдельном процессе только обнаружение | 4 | 122,09 |
| CPU | захват + обнаружение + отслеживание | в отдельном процессе только обнаружение | 3 | 121,01 |
| CPU | полный пайплайн | в отдельном процессе только обнаружение | 2 | 94,29 |
| CPU | полный пайплайн | в отдельном процессе только обнаружение | 1 | 92,39 |
| CPU | захват + обнаружение + отслеживание | в отдельном процессе только обнаружение | 2 | 61,80 |
| CPU | захват + обнаружение + отслеживание | в отдельном процессе только обнаружение | 1 | 49,31 |
| GPU | полный пайплайн | в отдельном процессе только обнаружение | 4 | 4,24 |
| GPU | захват + обнаружение + отслеживание | в отдельном процессе только обнаружение | 4 | 3,57 |

## Графики
- `reports/linux_perf_matrix/summary/plots/speedup_cpu_detection_process_detector.png`
- `reports/linux_perf_matrix/summary/plots/speedup_cpu_full_process_detector.png`
- `reports/linux_perf_matrix/summary/plots/speedup_cpu_tracking_process_detector.png`
- `reports/linux_perf_matrix/summary/plots/speedup_cuda_0_detection_process_detector.png`
- `reports/linux_perf_matrix/summary/plots/speedup_cuda_0_full_process_detector.png`
- `reports/linux_perf_matrix/summary/plots/speedup_cuda_0_tracking_process_detector.png`
