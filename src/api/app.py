"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.config.logging_config import setup_logging
from src.config.settings import get_settings
from src.database.session import close_db, init_db

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("api_starting", env=settings.app_env)
    await init_db()
    yield
    await close_db()
    logger.info("api_shutdown")


def create_api_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Polymarket Intelligence Bot API",
        description="Admin API for the Polymarket Telegram Bot",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not settings.is_production else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    return app
