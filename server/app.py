"""FastAPI entry point. Browser code handles devices; Python owns the workflow."""

from __future__ import annotations

# Direct execution from server/ must enter through the package-aware launcher.
if __name__ == "__main__" and not __package__:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from server.runtime import main

    main()
    raise SystemExit(0)

import asyncio
from collections import deque
import hmac
import logging
import mimetypes
import time
from typing import Annotated
from urllib.parse import urlsplit

mimetypes.add_type("application/manifest+json", ".webmanifest")

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import Field, StringConstraints
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect

from .config import PROJECT_ROOT, load_settings
from .errors import AppError
from .models import Context, MAX_ANSWERS, Model, SpeechRequest
from .providers import Providers
from .scenario import CHECKLIST_DIMENSIONS, DEFAULT_CONTEXT, DIFFICULTY_LIST, FAMILIARITY_OPTIONS, PERSONA_LIST, SCENARIO, SCENARIOS
from .sessions import PracticeStore
from .speech import speech_segments

logger = logging.getLogger(__name__)

MAX_AUDIO = 5 * 1024 * 1024
AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav"}
RequestID = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{16,80}$")]


class Action(Model):
    request_id: RequestID = Field(alias="requestId")


class StartRequest(Action):
    context: Context


class AnswerRequest(Action):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class SegmentRequest(Model):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


def error_response(error: AppError):
    return JSONResponse({"error": {"code": error.code, "message": error.message}}, status_code=error.status)


class LocalMiddleware:
    def __init__(self, app, settings_loader, *, clock=time.monotonic):
        self.app = app
        self.settings_loader = settings_loader
        self.clock = clock
        self._rate_buckets: dict[str, deque[float]] = {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        host = headers.get(b"host", b"").decode("latin1")
        forwarded_proto = headers.get(b"x-forwarded-proto", b"").decode("latin1").split(",")[0].strip().lower()
        is_https = scope.get("scheme") == "https" or forwarded_proto == "https"
        security_headers = {
            "cache-control": "no-store", "x-content-type-options": "nosniff", "referrer-policy": "no-referrer",
            "permissions-policy": "microphone=(self), camera=()",
            "content-security-policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        }
        if is_https:
            security_headers["strict-transport-security"] = "max-age=31536000; includeSubDomains"

        async def secure_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [(key.encode(), value.encode()) for key, value in security_headers.items()]
            await send(message)

        try:
            try:
                settings = self.settings_loader()
            except ValueError:
                logger.exception("Failed to load server settings.")
                raise AppError(500, "Server configuration is invalid. Check .env settings and try again.", "CONFIGURATION_ERROR") from None
            parsed = urlsplit("http://" + host)
            allowed_hosts = {"localhost", "127.0.0.1", "::1", settings.host.lower(), *settings.allowed_hosts}
            if not host or (parsed.hostname or "").lower() not in allowed_hosts or parsed.username or parsed.password:
                raise AppError(403, "Use this app from its local server address.", "INVALID_ORIGIN")
            expected_origins = {f"http://{host}", f"https://{host}"}
            if b"origin" in headers and headers[b"origin"].decode("latin1") not in expected_origins:
                raise AppError(403, "Use the app from the same local address.", "INVALID_ORIGIN")
            path = scope["path"]
            is_top_level_navigation = (
                scope["method"] == "GET"
                and not path.startswith("/api/")
                and headers.get(b"sec-fetch-mode") == b"navigate"
                and headers.get(b"sec-fetch-dest") == b"document"
            )
            if headers.get(b"sec-fetch-site") == b"cross-site" and not is_top_level_navigation:
                raise AppError(403, "Cross-site requests are not accepted.", "INVALID_ORIGIN")
            is_protected_api = path.startswith("/api/") and path != "/api/config"
            if settings.demo_access_token and is_protected_api:
                candidate = headers.get(b"x-devbridge-token", b"").decode("latin1").strip()
                if not candidate:
                    auth_header = headers.get(b"authorization", b"").decode("latin1").strip()
                    if auth_header.lower().startswith("bearer "):
                        candidate = auth_header[7:].strip()
                if not candidate or not hmac.compare_digest(candidate, settings.demo_access_token):
                    raise AppError(401, "An access token is required to use this shared demo.", "ACCESS_REQUIRED")

            if settings.rate_limit_per_minute > 0 and is_protected_api:
                client_ip = (scope.get("client") or ("local", 0))[0] or "local"
                now = self.clock()
                cutoff = now - 60.0
                bucket = self._rate_buckets.setdefault(client_ip, deque())
                while bucket and bucket[0] <= cutoff:
                    bucket.popleft()
                if len(bucket) >= settings.rate_limit_per_minute:
                    raise AppError(429, "Too many requests for this demo window. Wait a moment and retry.", "RATE_LIMITED")
                bucket.append(now)
                if len(self._rate_buckets) > 1000:
                    for key in [k for k, items in self._rate_buckets.items() if not items or items[-1] <= cutoff]:
                        self._rate_buckets.pop(key, None)

            limit = MAX_AUDIO if path == "/api/transcribe" else 64 * 1024
            content_length = int(headers.get(b"content-length", b"0"))
            if content_length < 0:
                raise AppError(400, "Invalid Content-Length header.", "INVALID_INPUT")
            if content_length > limit:
                raise AppError(413, "This request is too large. Keep recordings under 5 MB.", "PAYLOAD_TOO_LARGE")
        except (ValueError, AppError) as error:
            return await error_response(error if isinstance(error, AppError) else AppError(400, "Invalid request headers.", "INVALID_INPUT"))(scope, receive, secure_send)

        # Validate chunked bodies before FastAPI reads them. Exceptions raised by
        # receive() are otherwise converted by Starlette into a generic 400.
        messages = []
        size = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] != "http.request":
                break
            size += len(message.get("body", b""))
            if size > limit:
                error = AppError(413, "This request is too large. Keep recordings under 5 MB.", "PAYLOAD_TOO_LARGE")
                return await error_response(error)(scope, receive, secure_send)
            if not message.get("more_body", False):
                break

        async def validated_receive():
            if messages:
                return messages.pop(0)
            return await receive()

        await self.app(scope, validated_receive, secure_send)


async def cancellable(request: Request, coroutine):
    """Cancel HTTPX/model work if the browser disconnects or presses Stop."""
    task = asyncio.create_task(coroutine)
    finished = asyncio.Event()

    async def watch_disconnect():
        while not finished.is_set():
            if await request.is_disconnected():
                return
            if not finished.is_set():
                await asyncio.sleep(0.03)

    watcher = asyncio.create_task(watch_disconnect())
    try:
        done, _ = await asyncio.wait((task, watcher), return_when=asyncio.FIRST_COMPLETED)
        if watcher in done:
            task.cancel()
            raise AppError(499, "This request was cancelled.", "REQUEST_CANCELLED")
        return await task
    except asyncio.CancelledError:
        if asyncio.current_task().cancelling():
            raise
        raise AppError(499, "This request was stopped. Continue when you are ready.", "REQUEST_CANCELLED") from None
    finally:
        # Starlette's is_disconnected() cancel scope can consume a cancellation.
        # The event also ends the watcher after a fast response or error.
        finished.set()
        for pending in (task, watcher):
            if not pending.done():
                pending.cancel()
        await asyncio.gather(task, watcher, return_exceptions=True)


def create_app(*, settings_loader=load_settings, provider_factory=Providers, store=None, mode="live", clock=time.monotonic):
    app = FastAPI(title="DevBridge", docs_url=None, redoc_url=None, openapi_url=None)
    practices = store or PracticeStore()
    app.state.practices = practices
    app.add_middleware(LocalMiddleware, settings_loader=settings_loader, clock=clock)

    @app.exception_handler(AppError)
    async def app_error(_request, error):
        return error_response(error)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, _error):
        return error_response(AppError(400, "Check the scenario fields and request values. A value is missing, unsupported or too long.", "INVALID_INPUT"))

    @app.exception_handler(ClientDisconnect)
    async def disconnected(_request, _error):
        return Response(status_code=499)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request, error):
        codes = {
            404: ("NOT_FOUND", "The requested resource was not found."),
            405: ("METHOD_NOT_ALLOWED", "This HTTP method is not allowed for this endpoint."),
        }
        code, message = codes.get(error.status_code, ("REQUEST_FAILED", "This request could not be completed."))
        return error_response(AppError(error.status_code, message, code))

    @app.exception_handler(Exception)
    async def unexpected_error(_request, _error):
        logger.exception("Unhandled error in request handler.")
        return error_response(AppError(500, "Something went wrong on the local server. Please try again.", "INTERNAL_ERROR"))

    @app.get("/api/config")
    async def configuration():
        practices.prune()
        settings = settings_loader()
        return {"mode": mode, "configured": {"gemini": bool(settings.gemini_key), "groq": bool(settings.groq_key), "coaching": bool(settings.gemini_key or settings.groq_key or settings.openrouter_key), "speech": bool(settings.groq_voice_key or settings.groq_key)}, "accessRequired": bool(settings.demo_access_token), "rateLimitPerMinute": settings.rate_limit_per_minute, "scenario": SCENARIO, "scenarios": SCENARIOS, "personas": PERSONA_LIST, "familiarityOptions": FAMILIARITY_OPTIONS, "difficulties": DIFFICULTY_LIST, "checklistDimensions": CHECKLIST_DIMENSIONS, "defaultContext": DEFAULT_CONTEXT, "maxAnswers": MAX_ANSWERS, "maxRecordingSeconds": 60}

    @app.post("/api/practice")
    async def start(body: StartRequest):
        return practices.create(body.context, body.request_id)

    @app.post("/api/practice/{session_id}/answer")
    async def answer(session_id: str, body: AnswerRequest):
        return practices.answer(session_id, body.text, body.request_id)

    @app.post("/api/practice/{session_id}/advance")
    async def advance(session_id: str, body: Action, request: Request):
        return await cancellable(request, practices.advance(session_id, body.request_id, provider_factory(settings_loader())))

    @app.post("/api/practice/{session_id}/finish")
    async def finish(session_id: str, body: Action):
        return practices.finish(session_id, body.request_id)

    @app.post("/api/practice/{session_id}/retry")
    async def retry(session_id: str, body: Action):
        return practices.retry(session_id, body.request_id)

    @app.post("/api/practice/{session_id}/stop")
    async def stop(session_id: str):
        return await practices.stop(session_id)

    @app.delete("/api/practice/{session_id}")
    async def reset(session_id: str):
        await practices.delete(session_id)
        return Response(status_code=204)

    @app.post("/api/speech/segments")
    async def segments(body: SegmentRequest):
        return {"segments": speech_segments(body.text)}

    @app.post("/api/speak")
    async def speak(body: SpeechRequest, request: Request):
        audio = await cancellable(request, provider_factory(settings_loader()).speak(body.text))
        return Response(audio, media_type="audio/wav")

    @app.post("/api/transcribe")
    async def transcribe(request: Request):
        mime = request.headers.get("content-type", "").split(";")[0].lower().strip()
        if mime not in AUDIO_TYPES:
            raise AppError(415, "Use a supported audio recording format.", "UNSUPPORTED_AUDIO")
        audio = await request.body()
        if len(audio) < 64:
            raise AppError(422, "The recording is empty or too short. Record another answer.", "EMPTY_RECORDING")
        text = await cancellable(request, provider_factory(settings_loader()).transcribe(audio, mime))
        return {"text": text}

    app.mount("/", StaticFiles(directory=PROJECT_ROOT / "web", html=True), name="web")
    return app


app = create_app()
