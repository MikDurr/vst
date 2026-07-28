"""FastAPI layer for stemsep.

Run: uvicorn api.main:app --reload --port 8020   (from the project root)

Port 8020 deliberately: the vocal training studio's API is on 8000 and
vocalign's is on 8010, and all three may well be running at once.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routes_separate import router as separate_router

app = FastAPI(title="stemsep API")

log = logging.getLogger("stemsep.api")

_ALLOWED_ORIGINS = ["http://localhost:5190", "http://127.0.0.1:5190",
                    "http://localhost:4190", "http://127.0.0.1:4190"]

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


app.include_router(separate_router)
