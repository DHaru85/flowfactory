"""FastAPI 宿主。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api.errors import auth_error_handler, http_exception_handler, stream_protocol_handler
from api.registry.application import ApplicationRegistry
from api.registry.scan import register_discovered, run_startup_hooks
from api.registry.service import ServiceRegistry
from api.sse.machine import StreamProtocolError
from service.auth.errors import AuthError


def create_app() -> FastAPI:
    apps = ApplicationRegistry()
    services = ServiceRegistry()
    register_discovered(apps, services)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await run_startup_hooks(apps, services)
        logger.info("应用层已启动 apps={}", apps.list_keys())
        yield

    application = FastAPI(title="FlowFactory", lifespan=lifespan)
    application.state.apps = apps
    application.state.services = services
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_exception_handler(AuthError, auth_error_handler)
    application.add_exception_handler(StreamProtocolError, stream_protocol_handler)
    application.add_exception_handler(HTTPException, http_exception_handler)

    @application.get("/health")
    async def health() -> dict[str, object]:
        checks: dict[str, bool] = {}
        for svc in services.all():
            checks[svc.service_key] = await svc.health_check()
        ready = all(checks.values()) if checks else True
        return {
            "status": "ok" if ready else "degraded",
            "apps": apps.list_keys(),
            "services": checks,
        }

    for item in apps.all():
        application.include_router(item.build_router())
    return application


app = create_app()
