"""The FastAPI application.

At Phase 0 this exposes only a health endpoint, which is what `docker compose up`
and the compose healthcheck need. The line, state, action, forecast and evidence
routers arrive at T-080 and T-081.
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

SERVICE_NAME = "digitaltwin-api"


class Health(BaseModel):
    """What the service can answer for right now."""

    service: str
    status: Literal["OK", "DEGRADED"]
    build_phase: str


app = FastAPI(title="DigitalTwin.ai", docs_url="/docs", redoc_url=None)


@app.get("/health")
def health() -> Health:
    """Report whether the service is up and which part of the build it carries."""
    return Health(service=SERVICE_NAME, status="OK", build_phase="0")
