"""Job Switch Agent backend entrypoint (FastAPI)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analysis, applications, auth, documents, jobs
from app.config import get_settings
from app.database.database import get_database
from app.services.langsmith_setup import configure_langsmith
from app.services.phoenix_setup import configure_phoenix


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_langsmith(settings)
        configure_phoenix(settings)
        get_database()
        yield

    application = FastAPI(
        title="Job Switch Agent",
        version="0.1.0",
        description=(
            "Multi-agent career assistant: analyzes a resume against a job "
            "description, computes a transparent match score and builds a "
            "personalized 30-day preparation roadmap."
        ),
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(auth.router)
    application.include_router(documents.router)
    application.include_router(analysis.router)
    application.include_router(jobs.router)
    application.include_router(applications.router)

    @application.get("/health", tags=["health"])
    def health() -> dict:
        provider = str(getattr(settings, "llm_provider", "gemini") or "gemini").lower()
        if provider == "openrouter":
            model = settings.openrouter_model
        else:
            model = settings.model_name
        return {
            "status": "ok",
            "llm_provider": provider,
            "model": model,
        }

    return application


app = create_app()

