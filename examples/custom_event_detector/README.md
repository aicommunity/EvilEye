# Custom event detector (legacy in-tree example)

For a distributable plugin, use the entry-point workflow in
[`docs/PLUGINS.md`](../../docs/PLUGINS.md). The legacy decorator example below
emits `AlarmEvent` instances through generic persistence and journal display.

## Goal

Register a new event detector without editing `EventsService` hard-coded lists.

## Steps

1. Subclass `EventsDetector` (or compatible) and decorate with
   `@register_event_detector("MyName")` — see `heartbeat_event_detector.py`.
2. Import the module before runtime starts (`PYTHONPATH=examples/custom_event_detector`).
3. Enable in JSON:

```json
"events_detectors": {
  "enabled": ["CamEventsDetector", "ZoneEventsDetector", "HeartbeatEventDetector"],
  "HeartbeatEventDetector": {"interval_sec": 10}
}
```

When `enabled` is omitted, stock detectors start (backward compatible).

## Touch matrix (full product path)

| Layer | Used by this example |
|-------|----------------------|
| Detector class + legacy registry | yes |
| Generic alarm persistence | yes |
| Events journal | yes |
| Web journal | yes |
