import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.events import lifespan

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def create_app() -> FastAPI:
    app = FastAPI(title="Warden API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app
