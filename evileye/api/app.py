import os
from pathlib import Path
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from evileye.core.logger import get_module_logger
from evileye.api.routes.auth import router as auth_router
from evileye.api.routes.configs import router as configs_router
from evileye.api.routes.journals import router as journals_router
from evileye.api.routes.logs import router as logs_router
# from evileye.api.routes.pipelines import router as pipelines_router  # DEPRECATED
from evileye.api.routes.state import router as state_router
from evileye.api.routes.streaming import router as streaming_router
# from evileye.api.routes.events import router as events_router  # DEPRECATED
from evileye.api.routes.internal import router as internal_router
from evileye.api.core.config_run_access import get_config_run_manager
from evileye.api.security import (
    current_user,
    is_api_request_protected,
    load_web_auth_config,
    permissions_for_role,
    required_permissions_for_request,
)
from evileye import __version__

logger = get_module_logger("api.app")


class AuthGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        auth = request.app.state.web_auth
        path = request.url.path
        if not auth.enabled:
            return await call_next(request)
        if path.startswith("/api/v1/internal/") and auth.internal_token:
            supplied = request.headers.get("X-EvilEye-Internal-Token", "")
            if supplied != auth.internal_token:
                return Response('{"detail":"Invalid internal token"}', status_code=401, media_type="application/json")
            return await call_next(request)
        if path.startswith("/api/v1/internal/") and not auth.internal_token:
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

@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("FastAPI lifespan startup")
    
    try:
        yield
    finally:
        logger.info("FastAPI lifespan shutdown")
        try:
            get_config_run_manager().shutdown()
        except Exception as e:
            logger.error(f"Error during ConfigRunManager shutdown: {e}")


def create_app() -> FastAPI:
    app = FastAPI(title="EvilEye API", version=os.getenv("EVILEYE_API_VERSION", "v1"), lifespan=lifespan)
    logger.info("FastAPI app created")
    web_auth = load_web_auth_config()
    app.state.web_auth = web_auth
    allow_origins = os.getenv("EVILEYE_CORS_ALLOW_ORIGINS", "*").split(",")
    if web_auth.enabled and allow_origins == ["*"]:
        allow_origins = [
            "http://127.0.0.1",
            "http://localhost",
            "https://127.0.0.1",
            "https://localhost",
        ]
    app.add_middleware(AuthGuardMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=web_auth.session_secret,
        session_cookie=web_auth.cookie_name,
        same_site="lax",
        https_only=web_auth.secure_cookies,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("CORS middleware configured")

    @app.get("/ready")
    async def ready():
        return {"status": "ok"}

    @app.get("/api/v1/version")
    async def version():
        return {"evileye": __version__, "api": app.version}

    app.include_router(auth_router)
    app.include_router(state_router)
    app.include_router(journals_router)
    app.include_router(logs_router)
    app.include_router(configs_router)
    # app.include_router(pipelines_router)  # DEPRECATED: use /api/v1/configs/runs
    app.include_router(streaming_router)
    # app.include_router(events_router)  # DEPRECATED: requires in-process Controller access
    app.include_router(internal_router)
    logger.info("Routers registered: auth, state, journals, logs, configs, streaming, internal")

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="frontend")
        logger.info("Frontend static files mounted at /")
    else:
        logger.warning("Frontend not built: static dir missing. Run: cd evileye/api/frontend && npm install && npm run build")

    return app
