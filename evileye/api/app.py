import os
import threading
import asyncio
import json
import time
from pathlib import Path
from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from evileye.core.logger import get_module_logger
from evileye.core.runtime_services import get_frame_broker
from evileye.api.routes.auth import router as auth_router
from evileye.api.routes.configs import router as configs_router
from evileye.api.routes.config_editors import router as config_editors_router
from evileye.api.routes.journals import router as journals_router
from evileye.api.routes.logs import router as logs_router
from evileye.api.routes.users import router as users_router
from evileye.api.routes.bans import router as bans_router
from evileye.api.routes.state import router as state_router
from evileye.api.routes.streaming import router as streaming_router
from evileye.api.routes.realtime import router as realtime_router
from evileye.api.routes.playback import router as playback_router
from evileye.api.routes.internal import router as internal_router
from evileye.api.routes.setup import router as setup_router
from evileye.api.routes.system import router as system_router
from evileye.api.core.config_run_access import get_config_run_manager
from evileye.api.core.web_auth_bootstrap import ensure_default_admin_credentials
from evileye.api.core.ip_ban_store import get_ip_ban_store
from evileye.api.core.rate_guard import get_rate_guard, load_protection_config
from evileye.api.middleware.ip_protection import ProtectionMiddleware
from evileye.api.security import (
    current_user,
    is_api_request_protected,
    load_web_auth_config,
    permissions_for_role,
    required_permissions_for_request,
)
from evileye import __version__
from evileye.core.paths import creds_path

logger = get_module_logger("api.app")


class AuthGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        import hmac

        auth = request.app.state.web_auth
        path = request.url.path
        if not auth.enabled:
            return await call_next(request)
        if path.startswith("/api/v1/internal/"):
            if not auth.internal_token:
                return Response(
                    '{"detail":"Internal token not configured"}',
                    status_code=401,
                    media_type="application/json",
                )
            supplied = request.headers.get("X-EvilEye-Internal-Token", "")
            expected = auth.internal_token
            if not isinstance(supplied, str):
                supplied = str(supplied or "")
            token_ok = len(supplied) == len(expected) and hmac.compare_digest(supplied, expected)
            if not token_ok:
                try:
                    get_rate_guard().record_internal_fail(request)
                except Exception:
                    pass
                return Response('{"detail":"Invalid internal token"}', status_code=401, media_type="application/json")
            return await call_next(request)
        if not is_api_request_protected(path):
            return await call_next(request)
        user = current_user(request)
        if user is None:
            return Response('{"detail":"Authentication required"}', status_code=401, media_type="application/json")
        needed = required_permissions_for_request(path, request.method)
        granted = set(user.get("permissions") or permissions_for_role(str(user.get("role") or "user")))
        if needed and not needed.issubset(granted):
            return Response('{"detail":"Insufficient permissions"}', status_code=403, media_type="application/json")
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        csp = (
            "default-src 'self'; "
            "img-src 'self' blob: data:; "
            "media-src 'self' blob:; "
            "connect-src 'self' ws: wss:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "script-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers.setdefault("Content-Security-Policy", csp)
        from evileye.api.core.ssl_files import hsts_enabled

        if hsts_enabled():
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("FastAPI lifespan startup")
    ensure_default_admin_credentials()
    web_auth = load_web_auth_config()
    _app.state.web_auth = web_auth

    require_auth = os.getenv("EVILEYE_REQUIRE_AUTH", "").strip().lower() in {"1", "true", "yes"}
    is_production = os.getenv("EVILEYE_ENV", "").strip().lower() == "production"
    if (require_auth or is_production) and not web_auth.enabled:
        raise RuntimeError("web_auth.enabled must be true when EVILEYE_ENV=production or EVILEYE_REQUIRE_AUTH=1")

    try:
        creds_file = creds_path()
        section = {}
        if creds_file.exists():
            payload = json.loads(creds_file.read_text(encoding="utf-8"))
            section = payload.get("web_auth") if isinstance(payload, dict) else {}
        get_rate_guard().configure(load_protection_config(section if isinstance(section, dict) else {}))
    except Exception as exc:
        logger.warning("Failed to load protection config: %s", exc)

    cleanup_stop = threading.Event()

    def _broker_cleanup_loop():
        while not cleanup_stop.wait(5.0):
            try:
                get_frame_broker().purge_stale_frames(30.0)
            except Exception:
                continue
            try:
                get_ip_ban_store().prune_expired()
            except Exception:
                continue

    cleanup_thread = threading.Thread(target=_broker_cleanup_loop, daemon=True, name="FrameBrokerCleanup")
    cleanup_thread.start()

    from evileye.api.core.live_preview_hub import get_live_preview_hub

    hub = get_live_preview_hub()
    loop = asyncio.get_running_loop()
    hub.start(loop)
    try:
        from evileye.api.routes.realtime import make_hub_demand_callback

        hub.set_demand_callback(make_hub_demand_callback(_app))
    except Exception:
        pass
    get_frame_broker().set_publish_listener(hub.on_broker_publish)
    _app.state.live_preview_hub = hub

    try:
        from evileye.api.core.internal_unix import start_internal_unix_server

        start_internal_unix_server(getattr(_app.state.web_auth, "internal_token", "") or "")
    except Exception as exc:
        logger.warning("Internal unix frame relay not started: %s", exc)

    try:
        from evileye.core.mp_session_registry import cleanup_stale_sessions

        cleaned = cleanup_stale_sessions()
        if cleaned:
            logger.info("Cleaned %d stale MP worker process(es) on startup", cleaned)
    except Exception as exc:
        logger.warning("MP stale session cleanup failed on startup: %s", exc)

    try:
        from evileye.api.core.runtime_registry import prune_stale_runtime_records

        pruned = prune_stale_runtime_records()
        if pruned:
            logger.info("Pruned %d stale runtime registry record(s) on startup", pruned)
    except Exception as exc:
        logger.warning("Runtime registry prune failed on startup: %s", exc)

    def _registry_prune_loop():
        while not cleanup_stop.wait(3600.0):
            try:
                from evileye.api.core.runtime_registry import prune_stale_runtime_records

                prune_stale_runtime_records()
            except Exception:
                continue

    registry_prune_thread = threading.Thread(
        target=_registry_prune_loop, daemon=True, name="RuntimeRegistryPrune"
    )
    registry_prune_thread.start()

    try:
        from evileye.api.core.server_state import start_background_runtime_discovery

        start_background_runtime_discovery()
    except Exception as exc:
        logger.warning("Background runtime discovery failed to start: %s", exc)

    try:
        from evileye.api.core.playback_index_warmer import start_detection_ticks_warmer

        start_detection_ticks_warmer()
    except Exception as exc:
        logger.warning("Detection ticks warmer failed to start: %s", exc)

    try:
        yield
    finally:
        cleanup_stop.set()
        try:
            from evileye.api.core.playback_index_warmer import stop_detection_ticks_warmer

            stop_detection_ticks_warmer()
        except Exception:
            pass
        try:
            from evileye.api.core.server_state import stop_background_runtime_discovery

            stop_background_runtime_discovery()
        except Exception:
            pass
        try:
            from evileye.api.core.live_preview_hub import get_live_preview_hub

            await get_live_preview_hub().stop()
        except Exception:
            pass
        try:
            from evileye.api.core.internal_unix import stop_internal_unix_server

            stop_internal_unix_server()
        except Exception:
            pass
        logger.info("FastAPI lifespan shutdown")
        try:
            get_config_run_manager().shutdown()
        except Exception as e:
            logger.error(f"Error during ConfigRunManager shutdown: {e}")

def _cors_origins(web_auth) -> list[str]:
    raw = os.getenv("EVILEYE_CORS_ALLOW_ORIGINS", "*")
    allow_origins = [o.strip() for o in raw.split(",") if o.strip()]
    is_production = os.getenv("EVILEYE_ENV", "").strip().lower() == "production"
    if is_production and allow_origins == ["*"]:
        raise RuntimeError("EVILEYE_CORS_ALLOW_ORIGINS must be set explicitly in production")
    if web_auth.enabled and allow_origins == ["*"]:
        port = os.getenv("EVILEYE_HTTP_PORT", "8181")
        allow_origins = [
            "http://127.0.0.1",
            "http://localhost",
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
            "https://127.0.0.1",
            "https://localhost",
            f"https://127.0.0.1:{port}",
            f"https://localhost:{port}",
        ]
    return allow_origins


def create_app() -> FastAPI:
    web_auth = load_web_auth_config()
    disable_docs = (
        os.getenv("EVILEYE_DISABLE_DOCS", "").strip().lower() in {"1", "true", "yes"}
        or web_auth.enabled
        or os.getenv("EVILEYE_ENV", "").strip().lower() == "production"
    )
    app = FastAPI(
        title="EvilEye API",
        version=os.getenv("EVILEYE_API_VERSION", "v1"),
        lifespan=lifespan,
        docs_url=None if disable_docs else "/docs",
        redoc_url=None if disable_docs else "/redoc",
        openapi_url=None if disable_docs else "/openapi.json",
    )
    logger.info("FastAPI app created")
    app.state.web_auth = web_auth

    try:
        creds_file = creds_path()
        section = {}
        if creds_file.exists():
            payload = json.loads(creds_file.read_text(encoding="utf-8"))
            section = payload.get("web_auth") if isinstance(payload, dict) else {}
        get_rate_guard().configure(load_protection_config(section if isinstance(section, dict) else {}))
    except Exception:
        pass

    allow_origins = _cors_origins(web_auth)

    # Starlette: last added = outermost. Desired order:
    # SecurityHeaders -> CORS -> TrustedHost? -> Session -> Protection -> AuthGuard -> routes
    app.add_middleware(AuthGuardMiddleware)
    app.add_middleware(ProtectionMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=web_auth.session_secret,
        session_cookie=web_auth.cookie_name,
        same_site="lax",
        https_only=web_auth.secure_cookies,
    )
    allowed_hosts = os.getenv("EVILEYE_ALLOWED_HOSTS", "").strip()
    if allowed_hosts:
        hosts = [h.strip() for h in allowed_hosts.split(",") if h.strip()]
        if hosts:
            app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Export-Truncated"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    logger.info("CORS / protection / security headers middleware configured")

    @app.get("/ready")
    async def ready():
        payload: dict = {"status": "ok"}
        try:
            from evileye.api.core.internal_unix import internal_socket_path
            from evileye.api.routes.playback import detections_inflight_count, media_inflight_count

            broker = get_frame_broker()
            stats = broker.get_runtime_stats() if hasattr(broker, "get_runtime_stats") else {}
            keys = int(stats.get("frames_keys") or stats.get("frame_count") or 0)
            max_age = None
            try:
                # Prefer public helpers when present.
                if hasattr(broker, "max_frame_age_sec"):
                    max_age = broker.max_frame_age_sec()
                else:
                    with broker._lock:  # noqa: SLF001
                        frames = getattr(broker, "_frames", {}) or {}
                        keys = len(frames)
                        now = time.time()
                        ages = [
                            max(0.0, now - float(fr.timestamp))
                            for fr in frames.values()
                            if getattr(fr, "timestamp", None) is not None
                        ]
                        max_age = max(ages) if ages else None
            except Exception:
                pass
            sock_path = internal_socket_path()
            payload["frame_broker"] = {
                "keys": keys,
                "max_age_sec": max_age,
                "published_payloads": stats.get("published_payloads"),
                "estimated_bytes": stats.get("estimated_bytes"),
            }
            payload["internal_unix"] = {
                "listening": bool(sock_path.exists()),
                "path": str(sock_path),
            }
            payload["playback_detections_inflight"] = detections_inflight_count()
            payload["playback_media_inflight"] = media_inflight_count()
            try:
                from evileye.api.core.rate_guard import get_rate_guard

                payload["ws_reject_counts"] = get_rate_guard().ws_reject_counts()
            except Exception:
                pass
        except Exception:
            pass
        return payload

    @app.get("/api/v1/version")
    async def version():
        return {"evileye": __version__, "api": app.version}

    app.include_router(auth_router)
    app.include_router(state_router)
    app.include_router(journals_router)
    app.include_router(logs_router)
    app.include_router(users_router)
    app.include_router(bans_router)
    app.include_router(config_editors_router)
    app.include_router(configs_router)
    app.include_router(setup_router)
    app.include_router(system_router)
    app.include_router(streaming_router)
    app.include_router(realtime_router)
    app.include_router(playback_router)
    app.include_router(internal_router)
    logger.info(
        "Routers registered: auth, state, journals, logs, users, bans, config_editors, configs, setup, system, streaming, realtime, playback, internal"
    )

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{full_path:path}")
        async def spa_or_static(full_path: str, request: Request):
            if full_path.startswith("api/") or full_path in {"ready"}:
                return Response('{"detail":"Not Found"}', status_code=404, media_type="application/json")
            candidate = (static_dir / full_path).resolve()
            try:
                candidate.relative_to(static_dir.resolve())
            except ValueError:
                return Response("Forbidden", status_code=403)
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            index = static_dir / "index.html"
            if index.exists():
                return FileResponse(index)
            return Response("Frontend not built", status_code=404)

        logger.info("Frontend static files + SPA fallback mounted")
    else:
        logger.warning(
            "Frontend not built: static dir missing. Run: cd evileye/api/frontend && npm install && npm run build"
        )

    return app
