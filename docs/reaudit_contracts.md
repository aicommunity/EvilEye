# Reaudit contracts (R01–R17 / T19)

## Media ACL

- Authorize only after `Path.resolve()` under the data root (`Streams/` / `Events/`).
- Composite folders `CamA-CamB` require **all** parts in the caller ACL.
- Paths without an extractable owner (legacy journal media, `Metadata/*.json` as video) → **403**.
- Responses use `Cache-Control: private, no-store`.

## Live preview subscribe

- Empty `source_ids` means **subscribe none**, never “all cameras”.
- Until IntersectionObserver is ready, tiles are inactive → empty subscribe.
- On `subscribe` / `ping`, ACL is re-read; pending frames are cleared on set; sender skips sources not in the current set.
- Restricted user with empty ACL closes with **4403**.

## Playback memory cache

- Entry: `(fresh_until | None, stale_until, value, nbytes)`.
- `remember(ttl=None)` sticky: never fresh for `require_fresh`, kept until `stale_until`.
- `recall(require_fresh=True)` miss does **not** pop the entry (stale fallback remains).
- Oversized single entries are rejected; eviction uses stored nbytes.

## Event / detection indexes

- Singleflight builds the **full day**; callers project by camera after.
- Event payload includes `complete=true` and `covered_cameras` (includes empty cameras).
- Detection ticks reload when `source_mtime` changes (not only missing cams).
- HTTP presentation may still cap events; index builder uses `presentation_cap=None`.

## Auth scope (SPA)

- Login / logout / 401 refresh / ACL revision (same user, changed `allowed_cameras` or `camera_access`) bumps `authEpoch`.
- Sensitive `dataCache` keys are prefixed with `auth:{user}|e{epoch}:…` via `withAuthScope`.
- In-flight fetches registered with `trackAuthAbort` are aborted on bump; fetch handlers discard results when epoch changes.
- Live preview frames/etags clear on scope change; do not rely on page-local effects alone.
