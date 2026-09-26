# Custom event detector (dry-run)

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

| Layer | Required for dry-run | Required for journals/DB/GUI |
|-------|----------------------|------------------------------|
| Detector class + registry | yes | yes |
| JSON adapter | no | yes (`database_controller/json_adapter_*.py`) |
| DB adapter | no | yes |
| GUI journal tab | no | yes |
| Web journals | no | yes |
