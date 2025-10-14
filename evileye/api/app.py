import os
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from evileye.core.logger import get_module_logger
from evileye.api.routes.configs import router as configs_router
from evileye.api.routes.pipelines import router as pipelines_router
from evileye.api.routes.streaming import router as streaming_router
from evileye.api.core.manager_access import get_manager
from evileye import __version__

logger = get_module_logger("api.app")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API startup sequence initiated")
    try:
        yield
    finally:
        logger.info("API shutdown sequence initiated")
        try:
            get_manager().shutdown()
            logger.info("All pipelines stopped successfully")
        except Exception as e:
            logger.error(f"Pipelines shutdown error: {e}")


def create_app() -> FastAPI:
    app = FastAPI(title="EvilEye API", version=os.getenv("EVILEYE_API_VERSION", "v1"), lifespan=lifespan)
    logger.info("FastAPI app created")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("EVILEYE_CORS_ALLOW_ORIGINS", "*").split(","),
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

    app.include_router(configs_router)
    app.include_router(pipelines_router)
    app.include_router(streaming_router)
    logger.info("Routers registered: configs, pipelines, streaming")

    return app

app = create_app()


