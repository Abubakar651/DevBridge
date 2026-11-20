"""Async Python adapters for Gemini and Groq. No credentials reach the client."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Callable

import httpx
from pydantic import ValidationError

from .config import Settings
from .errors import AppError
from .models import Context, Feedback, RoleplayResponse, validate_feedback
from .prompts import COACH_PROMPT, ROLEPLAY_PROMPT

logger = logging.getLogger(__name__)
AUDIO_EXTENSIONS = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}


def _parse_json_output(content: str):
    """Parse JSON model output, stripping optional Markdown code fences."""
    text = content.strip()
    fenced = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", text, re.S | re.I)
    if fenced:
        text = fenced.group(1).strip()
    return json.loads(text)


class Providers:
    def __init__(self, settings: Settings, *, transport=None, diagnostic: Callable | None = None, fallback_enabled=True):
        self.settings = settings
        self.transport = transport
        self.diagnostic = diagnostic
        self.fallback_enabled = fallback_enabled
        self.reasoning_events = []

    async def request(self, method: str, url: str, *, audio=False, retry_on_429=False, **kwargs):
        try:
            async with asyncio.timeout(self.settings.timeout_seconds):
                async with httpx.AsyncClient(transport=self.transport, timeout=self.settings.timeout_seconds, follow_redirects=False) as client:
                    retryable = (429, 502, 503, 504) if retry_on_429 else (502, 503, 504)
                    for attempt in range(2):
                        response = await client.request(method, url, **kwargs)
                        if response.status_code not in retryable or attempt == 1:
                            break
                        delay = self.settings.retry_delay_seconds
                        if response.status_code == 429:
                            raw_retry = response.headers.get("retry-after", "")
                            try:
                                delay = min(max(float(raw_retry), 0.0), 2.0) if raw_retry else (0.0 if delay == 0 else min(max(delay, 0.5), 2.0))
                            except ValueError:
                                delay = 0.0 if delay == 0 else min(max(delay, 0.5), 2.0)
                        await asyncio.sleep(delay)
                    if not response.is_success:
                        try:
                            body = response.json()
                        except ValueError:
                            body = {}
                        upstream = body.get("error", {}) if isinstance(body, dict) else {}
                        if not isinstance(upstream, dict):
                            upstream = {}
                        if self.diagnostic:
                            message = str(upstream.get("message", "No diagnostic message."))
                            for key in (self.settings.gemini_key, self.settings.groq_key, self.settings.groq_voice_key):
                                if key:
                                    message = message.replace(key, "[redacted]")
                            message = re.sub(r"(?:gsk_[A-Za-z0-9_-]+|AIza[A-Za-z0-9_-]+)", "[redacted]", message)
                            self.diagnostic({"status": response.status_code, "code": upstream.get("code", upstream.get("status")), "message": message[:600]})
                        if upstream.get("code") == "model_terms_required":
                            raise AppError(503, "Groq voice needs an organization admin to review and accept the Orpheus model terms in the Groq console. Turn spoken replies off to continue in text.", "MODEL_TERMS_REQUIRED")
                        if response.status_code in (401, 403):
                            raise AppError(502, "The provider rejected access. Check the server key, model permissions and account setup.", "PROVIDER_ACCESS")
                        if response.status_code == 429:
                            raise AppError(429, "The provider is busy or a usage limit was reached. Wait a moment, then retry this step.", "PROVIDER_RATE_LIMIT")
                        if response.status_code == 404:
                            raise AppError(502, "The configured model is unavailable. Check its model ID in the server configuration.", "PROVIDER_MODEL")
                        if response.status_code == 503:
                            raise AppError(503, "The model is experiencing high demand. Retry this step later; your accepted answers are preserved.", "PROVIDER_BUSY")
                        raise AppError(502, "The provider could not complete this step. Please retry.", "PROVIDER_ERROR")
                    if audio:
                        return response.content
                    try:
                        return response.json()
                    except ValueError:
                        raise AppError(502, "The provider returned an unreadable response. Please retry.", "INVALID_PROVIDER_OUTPUT") from None
        except (TimeoutError, httpx.TimeoutException):
            raise AppError(504, "This step timed out. Retry it without submitting your answer again.", "PROVIDER_TIMEOUT") from None
        except httpx.RequestError:
            raise AppError(502, "Could not reach the provider. Check the connection and retry this step.", "PROVIDER_NETWORK") from None

    async def gemini(self, system: str, payload: dict, schema: dict):
        if not self.settings.gemini_key:
            raise AppError(503, "Gemini is not configured yet. Add its API key on the server, then refresh this page.", "GEMINI_NOT_CONFIGURED")
        generation = {"temperature": 0.4, "max_output_tokens": 4096}
        if re.match(r"^gemini-[34]", self.settings.gemini_model):
            generation.update(thinking_level="low", thinking_summaries="none")
        data = await self.request(
            "POST", "https://generativelanguage.googleapis.com/v1beta/interactions",
            headers={"Content-Type": "application/json", "x-goog-api-key": self.settings.gemini_key, "Api-Revision": "2026-05-20"},
            json={"model": self.settings.gemini_model, "store": False, "system_instruction": system, "input": json.dumps(payload), "response_format": {"type": "text", "mime_type": "application/json", "schema": schema}, "generation_config": generation},
        )
        try:
            if data["status"] != "completed":
                raise ValueError("Incomplete interaction")
            content = "".join(part.get("text", "") for step in data["steps"] if step.get("type") == "model_output" for part in step.get("content", []) if part.get("type") == "text")
            return _parse_json_output(content)
        except (KeyError, TypeError, ValueError, AttributeError):
            raise AppError(502, "The model did not finish a readable response. Please retry this step.", "INVALID_PROVIDER_OUTPUT") from None

    async def roleplay(self, context: Context, history: list[dict]) -> str:
        def validate(value):
            try:
                reply = RoleplayResponse.model_validate(value).reply
                if reply.count("?") != 1:
                    raise ValueError("The stakeholder must ask one question.")
                return reply
            except (ValidationError, ValueError):
                raise AppError(502, "The stakeholder response was incomplete. Please retry.", "INVALID_PROVIDER_OUTPUT", validation_hint="Ask exactly one short question as the project manager; do not deliver the learner's update or make their recommendation.") from None

        return await self.reasoning(ROLEPLAY_PROMPT, {"context": context.model_dump(by_alias=True), "history": history}, RoleplayResponse.model_json_schema(), validate, task="roleplay")

    async def coach(self, context: Context, history: list[dict], previous_history: list[dict] | None = None) -> Feedback:
        return await self.reasoning(COACH_PROMPT, {"context": context.model_dump(by_alias=True), "currentAttempt": history, "previousAttempt": previous_history}, Feedback.model_json_schema(), lambda value: validate_feedback(value, history, context, previous_history), task="coach")

    async def groq_reasoning(self, system: str, payload: dict, schema: dict):
        if not self.settings.groq_key:
            raise AppError(503, "The backup coach is not configured. Add a Groq API key on the server.", "GROQ_NOT_CONFIGURED")
        data = await self.request(
            "POST", "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.groq_key}"},
            json={
                "model": self.settings.groq_reasoning_model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload)}],
                "response_format": {"type": "json_schema", "json_schema": {"name": "voice_coach", "strict": True, "schema": schema}},
                "reasoning_effort": "medium", "temperature": 0.4, "max_completion_tokens": 4096,
            },
        )
        try:
            choice = data["choices"][0]
            if choice["finish_reason"] != "stop":
                raise ValueError("Incomplete completion")
            return _parse_json_output(choice["message"]["content"])
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            raise AppError(502, "The backup model did not finish a readable response. Please retry this step.", "INVALID_PROVIDER_OUTPUT") from None

    async def reasoning(self, system, payload, schema, validate, *, task):
        """Use the same inputs and validators on both providers; cancellation never falls back."""
        selected, model = "gemini", self.settings.gemini_model
        try:
            result = validate(await self.gemini(system, payload, schema))
        except AppError as error:
            if not self.fallback_enabled or not self.settings.groq_key:
                raise
            event = {"event": "reasoning_fallback", "task": task, "from": "gemini", "to": "groq", "code": error.code, "model": self.settings.groq_reasoning_model}
            self.reasoning_events.append(event)
            if self.diagnostic:
                self.diagnostic(event)
            logger.warning("Gemini failed (%s); using Groq %s for %s.", error.code, self.settings.groq_reasoning_model, task)
            selected, model = "groq", self.settings.groq_reasoning_model
            for attempt in range(2):
                try:
                    result = validate(await self.groq_reasoning(system, payload, schema))
                    break
                except AppError as backup_error:
                    if backup_error.code != "INVALID_PROVIDER_OUTPUT" or attempt == 1:
                        raise
                    hint = backup_error.validation_hint or "Return a complete JSON response matching the supplied schema."
                    logger.warning("Groq output failed validation for %s; regenerating once.", task)
                    event = {"event": "reasoning_validation_retry", "task": task, "provider": "groq", "hint": hint}
                    self.reasoning_events.append(event)
                    if self.diagnostic:
                        self.diagnostic(event)
                    system += "\nSERVER VALIDATION: Your previous response was rejected. " + hint + " Regenerate from the original context and transcript. Copy evidence exactly, including punctuation. Keep existing readiness, timing and approval authority unchanged. Do not introduce an unprovided sprint, cycle, iteration, release, week, benefit or commitment."
        self.reasoning_events.append({"event": "reasoning_success", "task": task, "provider": selected, "model": model})
        return result

    async def speak(self, text: str) -> bytes:
        voice_keys = []
        for key in (self.settings.groq_voice_key, self.settings.groq_key):
            if key and key not in voice_keys:
                voice_keys.append(key)
        if not voice_keys:
            raise AppError(503, "Groq voice is not configured. Turn spoken replies off and practise in text.", "GROQ_NOT_CONFIGURED")
        audio = b""
        rate_limit_error = None
        for index, voice_key in enumerate(voice_keys):
            try:
                audio = await self.request(
                    "POST", "https://api.groq.com/openai/v1/audio/speech", audio=True, retry_on_429=True,
                    headers={"Authorization": f"Bearer {voice_key}"},
                    json={"model": self.settings.tts_model, "input": text, "voice": self.settings.voice, "response_format": "wav"},
                )
                break
            except AppError as error:
                has_backup_key = index + 1 < len(voice_keys)
                if error.code == "PROVIDER_RATE_LIMIT":
                    rate_limit_error = rate_limit_error or error
                if not has_backup_key or error.code not in {"MODEL_TERMS_REQUIRED", "PROVIDER_ACCESS", "PROVIDER_RATE_LIMIT"}:
                    if rate_limit_error and error.code in {"MODEL_TERMS_REQUIRED", "PROVIDER_ACCESS"}:
                        raise rate_limit_error from None
                    raise
                logger.warning("The preferred Groq voice credential failed (%s); trying the primary Groq credential.", error.code)
        if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
            raise AppError(502, "The voice provider returned invalid audio. Retry playback or continue in text.", "INVALID_PROVIDER_OUTPUT")
        return audio

    async def transcribe(self, audio: bytes, mime_type: str) -> str:
        if not self.settings.groq_key:
            raise AppError(503, "Groq transcription is not configured. Type your answer to continue.", "GROQ_NOT_CONFIGURED")
        base_mime = mime_type.split(";")[0].lower().strip()
        extension = AUDIO_EXTENSIONS.get(base_mime)
        if not extension:
            raise AppError(415, "Use a supported audio recording format.", "UNSUPPORTED_AUDIO")
        data = await self.request("POST", "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {self.settings.groq_key}"},
            files={"file": (f"answer.{extension}", audio, base_mime)},
            data={"model": self.settings.stt_model, "language": "en", "response_format": "json", "prompt": "Workplace project update, release, scope, software development, AI, machine learning, PDF export."})
        text = data.get("text", "") if isinstance(data, dict) else ""
        if not isinstance(text, str) or not text.strip():
            raise AppError(422, "No speech was transcribed. Record another answer or type it instead.", "EMPTY_TRANSCRIPT")
        if len(text) > 4000:
            raise AppError(422, "That answer is too long for this short practice. Try a shorter explanation.", "ANSWER_TOO_LONG")
        return text.strip()
