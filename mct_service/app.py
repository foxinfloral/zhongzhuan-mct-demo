"""FastAPI routes: /v1 primary, /v0 alias."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from .engine import estimate
from .feedback import export_feedback_day, process_feedback
from .normalize import CONTRACT_VERSION, ENGINE_VERSION, NormalizeError

app = FastAPI(title="MCT Service", version=ENGINE_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _estimate_handler(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid JSON body", "flags": {"labels": ["【缺项】请求体非 JSON"]}},
        )
    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={"error": "request must be a JSON object", "flags": {"labels": ["【缺项】请求体须为对象"]}},
        )
    try:
        result = estimate(body)
        return JSONResponse(content=result)
    except NormalizeError as e:
        return JSONResponse(
            status_code=400,
            content={"error": e.message, "flags": e.flags},
        )


async def _feedback_handler(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid JSON body", "flags": {"labels": ["【缺项】请求体非 JSON"]}},
        )
    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={"error": "request must be a JSON object", "flags": {"labels": ["【缺项】请求体须为对象"]}},
        )
    try:
        result = process_feedback(body)
        return JSONResponse(content=result)
    except NormalizeError as e:
        return JSONResponse(
            status_code=400,
            content={"error": e.message, "flags": e.flags},
        )


async def _feedback_export_handler(request: Request):
    date = request.query_params.get("date")
    if not date:
        return JSONResponse(
            status_code=400,
            content={"error": "date query param required (YYYY-MM-DD)", "flags": {"labels": ["【缺项】date"]}},
        )
    try:
        text = export_feedback_day(date)
        return PlainTextResponse(content=text, media_type="application/x-ndjson")
    except NormalizeError as e:
        return JSONResponse(
            status_code=400,
            content={"error": e.message, "flags": e.flags},
        )


async def _health_handler() -> dict[str, Any]:
    return {
        "ok": True,
        "contract_version": CONTRACT_VERSION,
        "engine_version": ENGINE_VERSION,
        "feedback_enabled": True,
    }


# Primary (architecture gate)
app.add_api_route("/v1/mct/estimate", _estimate_handler, methods=["POST"])
app.add_api_route("/v1/mct/feedback", _feedback_handler, methods=["POST"])
app.add_api_route("/v1/mct/feedback/export", _feedback_export_handler, methods=["GET"], response_model=None)
app.add_api_route("/v1/health", _health_handler, methods=["GET"])

# Alias (compat)
app.add_api_route("/v0/mct/estimate", _estimate_handler, methods=["POST"])
app.add_api_route("/v0/mct/feedback", _feedback_handler, methods=["POST"])
app.add_api_route("/v0/mct/feedback/export", _feedback_export_handler, methods=["GET"], response_model=None)
app.add_api_route("/v0/health", _health_handler, methods=["GET"])
