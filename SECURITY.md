# EvilEye Web UI / API Security

This document summarizes production hardening for the FastAPI web API and React SPA.

## Must-do for production

1. Set `web_auth.enabled=true` (or set `EVILEYE_ENV=production` / `EVILEYE_REQUIRE_AUTH=1` so startup fails otherwise).
2. Use HTTPS (`evileye service install` TLS wizard or `--ssl-certfile` / `--ssl-keyfile`). `web_auth.secure_cookies` is auto-enabled when SSL cert env/files are set. Do **not** enable HSTS (`server.hsts` / `EVILEYE_HSTS=1`) for LAN self-signed certs — only after clients trust the CA or you use a public certificate.
3. Ensure `web_auth.session_secret` and `web_auth.internal_token` are strong (auto-generated on bootstrap if missing/weak).
4. Set explicit `EVILEYE_CORS_ALLOW_ORIGINS` for non-localhost UI hosts (e.g. `https://192.168.1.50:8181,https://evileye.lan:8181`; required when `EVILEYE_ENV=production`).
5. Optionally set `EVILEYE_ALLOWED_HOSTS` (IP and DNS names, no scheme) and `EVILEYE_WEB_API_BASE` / `server.public_base_url` (do not rely on request `Host`). Import `certs/ca.crt` on operator machines when using the deploy self-signed mini-CA.
6. Change the one-time bootstrap admin password immediately (logged once at first start, or set `EVILEYE_BOOTSTRAP_ADMIN_PASSWORD`). The Web UI blocks further use until the password is changed when `must_change_password` is set on the user (bootstrap sets this flag). Use the forced password gate, **Settings** → change password, `POST /api/v1/auth/change-password`, or admin `PATCH /api/v1/users/admin` with a new `password`. Camera ACL (`allowed_cameras` by `source_name`) is enforced for non-admin users; see [`docs/WEB_UI_GUIDE.md`](docs/WEB_UI_GUIDE.md) and [`docs/CONFIGURATION_GUIDE.md`](docs/CONFIGURATION_GUIDE.md).

   - Existing installs without the flag are **not** forced (manual `credentials.json` edits are respected).
   - To clear the gate manually after editing the hash yourself, set `"must_change_password": false` on the user record.

## IP protection / bans

See `web_auth.protection` in [CONFIGURATION_GUIDE.md](docs/CONFIGURATION_GUIDE.md).

- Auto-bans: login brute-force, register flood, HTTP RPS, 401/403 storms, WS connect flood, bad internal token, oversized internal frames.
- Admin UI: `/admin/bans` (permission `bans:manage`).
- Persistence: `web_ip_bans.json` (gitignored).
- Rate-limit counters are in-process memory: prefer a single uvicorn worker (or sticky routing). Bans still persist to JSON across workers.

## Related docs

- [CONFIGURATION_GUIDE.md](docs/CONFIGURATION_GUIDE.md) — `web_auth`, `protection`
- [WEB_UI_GUIDE.md](docs/WEB_UI_GUIDE.md) — routes and permissions
