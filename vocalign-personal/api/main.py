"""FastAPI layer for vocalign.

Run: uvicorn api.main:app --reload --port 8010   (from the project root)

Port 8010 deliberately, not 8000 — the vocal training studio's API uses 8000,
and these are separate apps that may well be running at the same time.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routes_align import router as align_router

app = FastAPI(title="vocalign API")

log = logging.getLogger("vocalign.api")

_ALLOWED_ORIGINS = ["http://localhost:5180", "http://127.0.0.1:5180",
                    "http://localhost:4180", "http://127.0.0.1:4180"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _unhandled_exception(request, exc):
    """Turn any unhandled exception into a JSON 500 with a readable detail.

    Starlette runs this outside CORSMiddleware, so the response would
    otherwise carry no Access-Control-Allow-* header and the browser would
    show an opaque "Failed to fetch" instead of the real message.
    """
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    origin = request.headers.get("origin")
    headers = {"Access-Control-Allow-Origin": origin} if origin in _ALLOWED_ORIGINS else {}
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
        headers=headers,
    )


app.include_router(align_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
