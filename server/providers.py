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
from .scenario import resolve_persona

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
                            message = str(upstream.get("message") or "No diagnostic message.")
                            for key in (self.settings.gemini_key, self.settings.groq_key, self.settings.groq_voice_key, self.settings.openrouter_key):
                                if key:
                                    message = message.replace(key, "[redacted]")
                            message = re.sub(r"(?:gsk_[A-Za-z0-9_-]+|AIza[A-Za-z0-9_-]+|sk-or-v1-[A-Za-z0-9_-]+)", "[redacted]", message)
                            self.diagnostic({"status": response.status_code, "code": upstream.get("code", upstream.get("status")), "message": message[:600]})
                        if upstream.get("code") == "model_terms_required":
                            raise AppError(503, "Groq voice needs an organization admin to review and accept the Orpheus model terms in the Groq console. Turn spoken replies off to continue in text.", "MODEL_TERMS_REQUIRED")
                        if response.status_code == 402:
                            raise AppError(502, "The provider account reached its credit or spend limit.", "PROVIDER_QUOTA")
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
        self.last_roleplay_closed = False

        def validate(value):
            try:
                parsed = RoleplayResponse.model_validate(value)
                closed = bool(parsed.closed and history)
                expected_q = 0 if closed else 1
                if parsed.reply.count("?") != expected_q:
                    raise ValueError("Question count mismatch.")
                self.last_roleplay_closed = closed
                return parsed.reply
            except (ValidationError, ValueError):
                raise AppError(502, "The stakeholder response was incomplete. Please retry.", "INVALID_PROVIDER_OUTPUT", validation_hint="Ask exactly one short question with closed=false, or wrap up politely with zero question marks and closed=true.") from None

        persona = resolve_persona(context.scenario_id, context.persona_id)
        roleplay_persona = {key: persona[key] for key in ("id", "label", "priorities", "noticesFirst", "evidenceBar", "openingStyle", "pushbackTriggers")}
        return await self.reasoning(ROLEPLAY_PROMPT, {"stakeholder": persona["label"], "persona": roleplay_persona, "context": context.model_dump(by_alias=True, exclude_none=True), "history": history}, RoleplayResponse.model_json_schema(), validate, task="roleplay")

    async def coach(self, context: Context, history: list[dict], previous_history: list[dict] | None = None) -> Feedback:
        persona = resolve_persona(context.scenario_id, context.persona_id)
        coach_persona = {key: persona[key] for key in ("id", "label", "priorities", "coachingFocus")}
        return await self.reasoning(COACH_PROMPT, {"stakeholder": persona["label"], "persona": coach_persona, "context": context.model_dump(by_alias=True, exclude_none=True), "currentAttempt": history, "previousAttempt": previous_history}, Feedback.model_json_schema(), lambda value: validate_feedback(value, history, context, previous_history), task="coach")

    async def _chat_completion_reasoning(self, *, url: str, api_key: str, not_configured_code: str, not_configured_message: str, model: str, system: str, payload: dict, schema: dict, extra_body: dict | None = None):
        if not api_key:
            raise AppError(503, not_configured_message, not_configured_code)
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload)}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "voice_coach", "strict": True, "schema": schema}},
            "reasoning_effort": "medium", "temperature": 0.4, "max_completion_tokens": 4096,
            **(extra_body or {}),
        }
        data = await self.request("POST", url, headers={"Authorization": f"Bearer {api_key}"}, json=body)
        try:
            choice = data["choices"][0]
            if choice["finish_reason"] != "stop":
                logger.warning("Chat completion stopped with finish_reason=%r (provider=%r).", choice.get("finish_reason"), data.get("provider"))
                raise ValueError("Incomplete completion")
            return _parse_json_output(choice["message"]["content"])
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            logger.warning("Unreadable chat completion output from provider=%r.", data.get("provider") if isinstance(data, dict) else None)
            raise AppError(502, "The backup model did not finish a readable response. Please retry this step.", "INVALID_PROVIDER_OUTPUT") from None

    async def groq_reasoning(self, system: str, payload: dict, schema: dict):
        return await self._chat_completion_reasoning(
            url="https://api.groq.com/openai/v1/chat/completions",
            api_key=self.settings.groq_key,
            not_configured_code="GROQ_NOT_CONFIGURED",
            not_configured_message="The backup coach is not configured. Add a Groq API key on the server.",
            model=self.settings.groq_reasoning_model,
            system=system, payload=payload, schema=schema,
        )

    async def openrouter_reasoning(self, system: str, payload: dict, schema: dict):
        return await self._chat_completion_reasoning(
            url="https://openrouter.ai/api/v1/chat/completions",
            api_key=self.settings.openrouter_key,
            not_configured_code="OPENROUTER_NOT_CONFIGURED",
            not_configured_message="OpenRouter is not configured. Add an OpenRouter API key on the server.",
            model=self.settings.openrouter_model,
            system=system, payload=payload, schema=schema,
            extra_body={"provider": {"require_parameters": True}},
        )

    async def _run_backup_with_retry(self, provider_name: str, caller, system: str, payload: dict, schema: dict, validate, *, task: str):
        for attempt in range(2):
            try:
                return validate(await caller(system, payload, schema))
            except AppError as backup_error:
                if backup_error.code != "INVALID_PROVIDER_OUTPUT" or attempt == 1:
                    raise
                hint = backup_error.validation_hint or "Return a complete JSON response matching the supplied schema."
                logger.warning("%s output failed validation for %s; regenerating once.", provider_name.capitalize(), task)
                event = {"event": "reasoning_validation_retry", "task": task, "provider": provider_name, "hint": hint}
                self.reasoning_events.append(event)
                if self.diagnostic:
                    self.diagnostic(event)
                system += "\nSERVER VALIDATION: Your previous response was rejected. " + hint + " Regenerate from the original context and transcript. Copy evidence exactly, including punctuation. Keep existing readiness, timing and approval authority unchanged. Do not introduce an unprovided sprint, cycle, iteration, release, week, benefit or commitment."

    async def reasoning(self, system, payload, schema, validate, *, task):
        """Use the same inputs and validators across Gemini, Groq, and OpenRouter; cancellation never falls back."""
        selected, model = "gemini", self.settings.gemini_model
        try:
            result = validate(await self.gemini(system, payload, schema))
        except AppError as error:
            backups = []
            if self.settings.groq_key:
                backups.append(("groq", self.settings.groq_reasoning_model, self.groq_reasoning))
            if self.settings.openrouter_key:
                backups.append(("openrouter", self.settings.openrouter_model, self.openrouter_reasoning))
            if not self.fallback_enabled or not backups:
                raise
            current_error = error
            previous_provider = "gemini"
            for index, (backup_name, backup_model, caller) in enumerate(backups):
                event = {"event": "reasoning_fallback", "task": task, "from": previous_provider, "to": backup_name, "code": current_error.code, "model": backup_model}
                self.reasoning_events.append(event)
                if self.diagnostic:
                    self.diagnostic(event)
                logger.warning("%s failed (%s); using %s %s for %s.", previous_provider.capitalize(), current_error.code, backup_name, backup_model, task)
                selected, model = backup_name, backup_model
                try:
                    result = await self._run_backup_with_retry(backup_name, caller, system, payload, schema, validate, task=task)
                    break
                except AppError as backup_error:
                    if index + 1 == len(backups):
                        raise
                    current_error = backup_error
                    previous_provider = backup_name
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
            data={"model": self.settings.stt_model, "language": "en", "response_format": "json", "prompt": "Workplace update, client scope, IT operations, support handover, AI pilot, human review, contribution, workload, customer churn, CRM rollout."})
        text = data.get("text", "") if isinstance(data, dict) else ""
        if not isinstance(text, str) or not text.strip():
            raise AppError(422, "No speech was transcribed. Record another answer or type it instead.", "EMPTY_TRANSCRIPT")
        if len(text) > 4000:
            raise AppError(422, "That answer is too long for this short practice. Try a shorter explanation.", "ANSWER_TOO_LONG")
        return text.strip()
