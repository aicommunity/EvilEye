import os
import atexit
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

def cleanup_pipelines():
    """Cleanup function for atexit handler"""
    try:
        logger.info("API shutdown sequence initiated (atexit)")
        get_manager().shutdown()
        logger.info("All pipelines stopped successfully (atexit)")
    except Exception as e:
        logger.error(f"Pipelines shutdown error (atexit): {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API startup sequence initiated")
    
    atexit.register(cleanup_pipelines)
    
    try:
        yield
    finally:
        logger.info("API shutdown sequence initiated (lifespan)")
        try:
            get_manager().shutdown()
            logger.info("All pipelines stopped successfully (lifespan)")
        except Exception as e:
            logger.error(f"Pipelines shutdown error (lifespan): {e}")        
        try:
            atexit.unregister(cleanup_pipelines)
        except ValueError as e:
            logger.debug(f"Handler not registered or already unregistered: {e}")
        except Exception as e:
            logger.error(f"Unregister atexit handler error (lifespan): {e}")      
        
        logger.info("API shutdown sequence completed")


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


