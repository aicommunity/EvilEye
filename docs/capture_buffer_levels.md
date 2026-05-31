# Capture buffer levels (R4 spike)

**Status:** keep three levels (2026-05); reduction deferred as TD-MP-401.

| Level | Component | Role |
|-------|-----------|------|
| 1 | `DropOldestQueue` (`queue_utils` + `queue_policy.put_drop_oldest_deque`) | Parent thread: prefer fresh frames |
| 2 | `MpControl` input/output queues | IPC to capture child |
| 3 | `mp_worker_capture` internal loop | Decode + pack SHM; output uses `put_drop_oldest` with `_release_packed_frame` on drop |

Removing level 1 without redesign risks stale frames in thread-mode capture. Removing level 2 breaks backpressure to the child.
