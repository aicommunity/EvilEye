# Shared-memory frame ownership (TD-PS-D2)

Status: design only. Runtime behaviour does not change with this note. The segment pool in `SharedFrameTransport` is already in place. What remains is skipping a second pixel copy when several process stages receive the same unchanged frame. That skip is not safe until a segment has a reference count.

## What happens today

`_prepare_item_for_process` in `evileye/core/plugin_runtime/transport.py` builds a descriptor for each `Frame`. If `image` is not `None`, it always calls `SharedFrameTransport.alloc_frame`, which copies the pixels into a segment (`view[:] = arr`). The descriptor sent to the worker has `image = None` and a `frame_handle`. The parent `Frame.image` stays set: capture and the UI share that array. Do not clear it on the IPC path.

Each process-mode `ItemModuleAdapter` owns its own `SharedFrameTransport`. When the worker reply arrives, `_release_process_request` calls `release_frame` on every handle of that request. With the pool enabled, the segment returns to the free list or is unlinked. Nothing counts how many stages still need the same name.

`consume_frame` copies the pixels and then `unlink`s the segment. That is a single-consumer operation. It cannot carry one segment across a later stage.

`FrameHandle` is a frozen dataclass of names and metadata. It has no reference count. `frame_id` is not a pixel-change marker: the same id can repeat inside a stage window. `connection_generation` advances on reconnect, not when preprocessing replaces pixels.

## Ownership to implement later

One segment per logical frame, owned by the parent. Each process stage that still needs those pixels holds a reference to the same `shm_name`. The segment returns to the pool, or is unlinked, only when the count reaches zero.

The freshness marker is the existing `frame_version`. Preprocessing already increments it when it replaces `image`. `frame_id` alone is not enough. The parent `Frame` should remember the version that was copied and the handle that holds that copy. `_FRAME_METADATA_FIELDS` already forwards `frame_version` onto the descriptor; it does not record which segment matches that version.

`alloc_frame` may be skipped only when all of these hold:

- the stored version equals the current `frame_version`;
- the handle still names a live segment;
- the reference count is greater than zero.

Any preprocessing bump, a dead handle, or a zero count means a new `alloc_frame`, as today.

`consume_frame` stays a copy-and-unlink helper for callers that truly consume a foreign segment. Multi-stage fanout must not use it to share a name.

## Out of this design

- Capture packing in `mp_worker_capture` and `pack_frame_for_worker`.
- `DetectionThreadYoloMp`.
- Clearing the parent `Frame.image`.
- Changing worker reads. `get_frame_view` still copies into the child; that is a separate saving and is not required to skip the parent `alloc_frame`.

## Test this design must make possible

Not written yet. The implementation cycle, after a real TD-PS-D6/D7 ratio exists, should add a test with two process adapters in a row on one `Frame`:

- without preprocessing, the second `put` does not call `alloc_frame` again;
- after `frame_version` increases, the next `put` does call `alloc_frame`.

A partial shortcut of the form "if `frame_handle` is set, skip `alloc_frame`" is rejected. The owner releases the segment when its own request completes, so the next stage would read a pooled or unlinked buffer.
