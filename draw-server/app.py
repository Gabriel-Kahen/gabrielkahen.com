"""Public write-only drawing API; run a single worker on loopback port 8012."""

from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import asyncio
import json
import os
from pathlib import Path
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from drawing import InvalidDrawing, PrinterConfig, validate_drawing
from storage import ConflictingSubmission, StorageFull, Store
from plot_queue import Queue

MAX_BODY_BYTES = 1_048_576
BODY_TIMEOUT_SECONDS = 15
PRODUCTION_ORIGINS = ("https://gabrielkahen.com", "https://www.gabrielkahen.com")


@dataclass(frozen=True)
class Settings:
    db_path: str = str(Path.home() / ".local/share/gabriel-draw/drawings.sqlite3")
    max_storage_bytes: int = 134_217_728
    max_drawings: int = 10_000
    requests_per_minute: int = 60
    extra_origins: tuple = ()
    printer: PrinterConfig = field(default_factory=PrinterConfig)

    def __post_init__(self):
        if not 1_048_576 <= self.max_storage_bytes <= 100 * 1024**3:
            raise ValueError("Storage cap must be between 1 MiB and 100 GiB.")
        if not 1 <= self.max_drawings <= 1_000_000 or not 1 <= self.requests_per_minute <= 10_000:
            raise ValueError("Invalid drawing or request cap.")
        if any(not origin.startswith(("http://", "https://")) or origin.endswith("/") for origin in self.extra_origins):
            raise ValueError("Extra CORS origins must be explicit HTTP(S) origins without a trailing slash.")

    @classmethod
    def from_env(cls):
        config_path = os.getenv("DRAW_PRINTER_CONFIG")
        config = PrinterConfig(**json.loads(Path(config_path).read_text())) if config_path else PrinterConfig()
        return cls(
            db_path=os.getenv("DRAW_DB_PATH", cls.db_path),
            max_storage_bytes=int(os.getenv("DRAW_MAX_STORAGE_BYTES", "134217728")),
            max_drawings=int(os.getenv("DRAW_MAX_DRAWINGS", "10000")),
            requests_per_minute=int(os.getenv("DRAW_REQUESTS_PER_MINUTE", "60")),
            extra_origins=tuple(origin.strip() for origin in os.getenv("DRAW_EXTRA_ORIGINS", "").split(",") if origin.strip()),
            printer=config,
        )


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON keys are not allowed.")
        result[key] = value
    return result


def create_app(settings=None):
    settings = settings or Settings.from_env()
    store = Store(settings.db_path, settings.max_storage_bytes, settings.max_drawings)
    requests = deque()
    origins = (*PRODUCTION_ORIGINS, *settings.extra_origins)

    @asynccontextmanager
    async def lifespan(app):
        await run_in_threadpool(store.initialize)
        yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    app.add_middleware(CORSMiddleware, allow_origins=list(origins), allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        return JSONResponse({"error": error.detail}, status_code=error.status_code, headers=error.headers)

    @app.get("/health")
    @app.get("/draw-api/health")
    async def health():
        return {"status": "ok", "version": 1}

    @app.post("/drawings")
    @app.post("/draw-api/drawings")
    async def submit(request: Request):
        origin = request.headers.get("origin")
        if origin is not None and origin not in origins:
            raise HTTPException(403, "Origin is not allowed.")
        # Deliberately global: proxies can hide client IPs and forwarded headers can be forged.
        now = time.monotonic()
        while requests and requests[0] <= now - 60:
            requests.popleft()
        if len(requests) >= settings.requests_per_minute:
            raise HTTPException(429, "Too many submissions. Try again in a minute.", headers={"Retry-After": "60"})
        requests.append(now)
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise HTTPException(415, "Send application/json.")
        if request.headers.get("content-encoding", "identity").lower() != "identity":
            raise HTTPException(415, "Compressed requests are not supported.")
        claimed = request.headers.get("content-length")
        if claimed is not None:
            try:
                size = int(claimed)
                if size < 0:
                    raise ValueError
            except ValueError:
                raise HTTPException(400, "Invalid Content-Length.") from None
            if size > MAX_BODY_BYTES:
                raise HTTPException(413, "Drawing request is too large.")
        body = bytearray()
        try:
            async with asyncio.timeout(BODY_TIMEOUT_SECONDS):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > MAX_BODY_BYTES:
                        raise HTTPException(413, "Drawing request is too large.")
                    body.extend(chunk)
        except TimeoutError:
            raise HTTPException(408, "Drawing upload timed out. Please try again.") from None
        try:
            data = json.loads(body, object_pairs_hook=unique_object)
            submission_id, strokes, length, canonical = validate_drawing(data)
        except (ValueError, RecursionError, UnicodeError) as error:
            detail = str(error) if isinstance(error, InvalidDrawing) else "Invalid JSON drawing."
            raise HTTPException(422, detail) from None
        try:
            receipt, created = await run_in_threadpool(store.save, submission_id, strokes, length, canonical, settings.printer)
        except ConflictingSubmission:
            raise HTTPException(409, "This submission ID was already used for a different drawing.") from None
        except StorageFull:
            raise HTTPException(503, "Drawing storage is full or busy. Please try again later.") from None
        printer_status = await run_in_threadpool(Queue(settings.db_path).receipt_status, submission_id)
        if printer_status:
            receipt["status"] = printer_status
        return JSONResponse(receipt, status_code=201 if created else 200, headers={"Cache-Control": "no-store"})

    return app


app = create_app()
