from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown


def create_app() -> FastAPI:
    app = FastAPI(title="EvilEye API", version=os.getenv("EVILEYE_API_VERSION", "v1"), lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("EVILEYE_CORS_ALLOW_ORIGINS", "*").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/ready")
    async def health_check():
        return {"status": "ok"}

    @app.get("/api/v1/version")
    async def version():
        from evileye import __version__

        return {"evileye": __version__, "api": app.version}

    return app

app = create_app()


