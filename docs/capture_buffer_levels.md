# Capture buffer levels (R4 spike)

**Status:** keep three levels (2026-05); reduction deferred as TD-MP-401.

| Level | Component | Role |
|-------|-----------|------|
| 1 | `DropOldestQueue` (`queue_utils` + `queue_policy.put_drop_oldest_deque`) | Parent thread: prefer fresh frames |
| 2 | `MpControl` input/output queues | IPC to capture child |
| 3 | `mp_worker_capture` internal loop | Decode + pack SHM; output uses `put_drop_oldest` with `_release_packed_frame` on drop |

Removing level 1 without redesign risks stale frames in thread-mode capture. Removing level 2 breaks backpressure to the child.

## How to measure before changing a level

Run one live RTSP source long enough to see overflow, and record three counters separately. Do not merge queues on the strength of this note.

1. Parent `DropOldestQueue`: count puts that drop an older frame before the frame reaches `MpControl`.
2. `MpControl` input and output: count IPC drops and the high-water mark of each queue.
3. `mp_worker_capture`: count `put_drop_oldest` drops inside the child, including frames released by `_release_packed_frame`.

A level is a candidate for removal only when its drop count stays at zero while another level absorbs the same bursts, and a thread-mode run still prefers a fresh frame over a stale one. Until those numbers exist, keep all three levels.
