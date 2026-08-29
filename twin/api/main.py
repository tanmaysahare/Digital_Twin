"""The FastAPI application.

Three things happen here and nothing else: the routers are mounted, the browser
is allowed to talk to the API from the web container's own origin, and errors
leave as RFC 9457 problem details whose `detail` is a sentence a supervisor can
read without a translation layer.

The twin itself starts on first use rather than at import, so that a process
which only wants `/health` (a container probe, a smoke test) does not simulate a
line to answer it.
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from twin.api.context import get_context
from twin.api.live_socket import socket_router
from twin.api.plan import plan_router
from twin.api.routes import router

SERVICE_NAME = "digitaltwin-api"

# The web container and a developer's browser. No wildcard: the product ships
# with a stated origin list rather than an open one, and SECURITY_REQUIREMENTS.md
# Section 6 says plainly what else is missing in the prototype.
# The web container, a developer's browser, and the alternate port a
# developer falls back to when 3000 is already taken on their machine.
ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3100",
    "http://127.0.0.1:3100",
    "http://web:3000",
)

PROBLEM_BASE = "https://digitaltwin.ai/problems"


class Health(BaseModel):
    """What the service can answer for right now."""

    service: str
    status: Literal["OK", "DEGRADED"]
    twin: Literal["WARMING", "LIVE", "FINISHED"]
    cycles: int
    behind_s: float


app = FastAPI(
    title="DigitalTwin.ai",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
    description=(
        "A live read-only digital twin of a mixed-model vehicle assembly line. "
        "Every value carries its provenance and no endpoint writes anywhere."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["content-type"],
)

app.include_router(router)
app.include_router(plan_router)
app.include_router(socket_router)


@app.exception_handler(StarletteHTTPException)
async def problem_detail(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """RFC 9457, with a `detail` written to be shown to a person."""
    return JSONResponse(
        status_code=exc.status_code,
        media_type="application/problem+json",
        content={
            "type": f"{PROBLEM_BASE}/{_slug(exc.status_code)}",
            "title": _title(exc.status_code),
            "status": exc.status_code,
            "detail": str(exc.detail),
            "instance": str(request.url.path),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_problem(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """A malformed request, named field by field rather than as a stack trace."""
    fields = ", ".join(
        ".".join(str(part) for part in error["loc"][1:]) for error in exc.errors()
    )
    return JSONResponse(
        status_code=422,
        media_type="application/problem+json",
        content={
            "type": f"{PROBLEM_BASE}/malformed-request",
            "title": "The request could not be read",
            "status": 422,
            "detail": f"Check these fields: {fields}.",
            "instance": str(request.url.path),
            "errors": [
                {
                    "field": ".".join(str(part) for part in error["loc"][1:]),
                    "problem": error["msg"],
                }
                for error in exc.errors()
            ],
        },
    )


def _slug(status: int) -> str:
    """The problem type for one status code."""
    return {
        404: "not-found",
        409: "insufficient-history",
        422: "malformed-request",
    }.get(status, "error")


def _title(status: int) -> str:
    """The problem title for one status code."""
    return {
        404: "Not found",
        409: "Not enough history yet",
        422: "The request could not be read",
    }.get(status, "The request could not be completed")


@app.get("/health", response_model=Health)
def health() -> Health:
    """Whether the service is up and how far behind the twin is."""
    status = get_context().twin.status()
    return Health(
        service=SERVICE_NAME,
        status="OK",
        twin="FINISHED" if status.finished else ("LIVE" if status.ready else "WARMING"),
        cycles=status.cycles,
        behind_s=round(status.behind_s, 1),
    )
