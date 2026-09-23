# Reaudit contracts (R01–R17 / T19 / F01–F13)

## Media ACL

- Authorize only after `Path.resolve()` under the data root (`Streams/` / `Events/` / `Detections/`).
- Object previews/frames from the writer live under `Detections/<date>/Images/{Found,Lost}{Previews,Frames}/` (not legacy).
- Event images may live under `Events/<date>/Images/...`.
- Composite folders `CamA-CamB` require **all** parts in the caller ACL when each part is a catalog camera.
- A hyphenated folder that matches a catalog name as a whole (e.g. `Cam-2`) is a **single** owner.
- Paths without an extractable owner for restricted users → **403**. Unrestricted (admin / auth-disabled) still requires an allowed root and media kind.
- Metadata JSON is never serveable as video/image.
- Responses use `Cache-Control: private, no-store`.

## Session principal / transports (F01)

- HTTP `current_user` revalidates the signed session against credentials **and** web user store (disabled / rejected / pending / role).
- Admin camera bypass uses the **live** record role, not the cookie role.
- Disable / demote / delete / reject / ACL shrink calls `revoke_user_transports`: live preview WS, metadata WS, and MJPEG (cancel on next frame).
- Already-in-flight WS frames may deliver one last chunk; MJPEG stops at the next frame boundary.

## Live preview subscribe

- Empty `source_ids` means **subscribe none**, never “all cameras”.
- Until IntersectionObserver is ready, tiles are inactive → empty subscribe.
- On `subscribe` / `ping`, ACL is re-read; `None` (unrestricted) is **not** deny (F03).
- Pending frames are cleared on set; sender skips sources not in the current set.
- Restricted user with empty ACL closes with **4403**.

## Playback memory cache

- Entry: `(fresh_until | None, stale_until, value, nbytes)`.
- `remember(ttl=None)` sticky: never fresh for `require_fresh`, kept until `stale_until`.
- `recall(require_fresh=True)` miss does **not** pop the entry (stale fallback remains).
- Oversized single entries are rejected; eviction uses stored nbytes.
- Route fallbacks must not re-`remember` stale as freshly computed (F10).

## Event / detection indexes

- Singleflight builds the **full day**; callers project by camera after (events and detections).
- Event payload includes `complete=true` and `covered_cameras` (includes empty cameras / negative coverage).
- Detection ticks reload when `source_mtime` changes (not only missing cams).
- HTTP presentation may still cap events; index builder uses `presentation_cap=None`.

## Auth scope (SPA)

- Login / logout / 401 refresh / ACL revision (same user, changed `allowed_cameras` or `camera_access`) bumps `authEpoch`.
- Sensitive `dataCache` keys are prefixed with `auth:{user}|e{epoch}:…` via `withAuthScope`.
- In-flight fetches registered with `trackAuthAbort` are aborted on bump; fetch handlers discard results when epoch changes.
- Live preview frames/etags clear on scope change; notify fetches abort per source; do not rely on page-local effects alone.
- Displayed journal rows and metadata stores clear on epoch; prefs (`visible_cameras`) ≠ hard ACL.
