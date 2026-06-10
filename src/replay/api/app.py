"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from replay.api import (
    routes_assist,
    routes_chat,
    routes_health,
    routes_keys,
    routes_orgs,
    routes_playground,
    routes_providers,
    routes_requests,
)
from replay.config import get_settings
from replay.logging import configure_logging
from replay.proxy.router import router as proxy_router


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Replay", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Conversation-Id"],
    )

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, object]:
        """Service banner and a map of the live surfaces."""
        return {
            "service": "replay",
            "version": "0.1.0",
            "tagline": "capture and replay your LLM traffic",
            "endpoints": {
                "health": "/health",
                "docs": "/docs",
                "management_api": "/api",
                "proxy": "/v1/messages",
            },
        }

    # Proxy hot path.
    app.include_router(proxy_router, tags=["proxy"])

    # Management API.
    app.include_router(routes_health.router, tags=["health"])
    app.include_router(routes_orgs.router, prefix="/api", tags=["orgs"])
    app.include_router(routes_keys.router, prefix="/api", tags=["keys"])
    app.include_router(routes_providers.router, prefix="/api", tags=["provider-keys"])
    app.include_router(routes_requests.router, prefix="/api", tags=["requests"])
    app.include_router(routes_playground.router, prefix="/api", tags=["playground"])
    app.include_router(routes_chat.router, prefix="/api", tags=["chat"])
    app.include_router(routes_assist.router, prefix="/api", tags=["assist"])

    return app


app = create_app()
