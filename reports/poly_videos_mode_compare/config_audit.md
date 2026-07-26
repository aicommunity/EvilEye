# Аудит конфигов poly-videos (process vs thread)

## Сравниваемые файлы

| Capture | Mode | Config |
| --- | --- | --- |
| opencv | process | `configs/poly-videos.json` |
| opencv | thread | `configs/poly-videos-thread.json` |
| gst | process | `configs/poly-videos-gst.json` |
| gst | thread | `configs/poly-videos-gst-thread.json` |

## Пары process/thread

### opencv: `configs/poly-videos.json` vs `configs/poly-videos-thread.json`
- Всего отличий: **13**
- Неожиданных (кроме execution_mode): **0**

Неожиданных отличий нет (только `execution_mode`).

### gst: `configs/poly-videos-gst.json` vs `configs/poly-videos-gst-thread.json`
- Всего отличий: **13**
- Неожиданных (кроме execution_mode): **0**

Неожиданных отличий нет (только `execution_mode`).

## Видеофайлы

- `configs/poly-videos.json`: **OK**
- `configs/poly-videos-thread.json`: **OK**
- `configs/poly-videos-gst.json`: **OK**
- `configs/poly-videos-gst-thread.json`: **OK**

## OpenCV vs GStreamer (справочно)

Между `poly-videos*.json` и `poly-videos-gst*.json` ожидаются отличия `type`, `apiPreference`, `gstreamer_*` и пути захвата — это разные backend.

- Число отличий opencv vs gst (базовые process-конфиги): **269**

## Preflight

- `validate_json_configs.py`: **OK**
