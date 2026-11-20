"""Authoritative practice workflow, attempts, retries and history live in Python."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from .errors import AppError
from .models import Context, Feedback, MAX_ANSWERS


@dataclass
class Attempt:
    number: int
    messages: list[dict] = field(default_factory=list)
    feedback: Feedback | None = None
    playback: dict | None = None


@dataclass
class Practice:
    session_id: str
    context: Context
    attempts: list[Attempt] = field(default_factory=lambda: [Attempt(1)])
    pending: str | None = "roleplay"
    generation: int = 0
    touched: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    inflight: asyncio.Task | None = None
    requests: OrderedDict = field(default_factory=OrderedDict)
    deleted: bool = False

    @property
    def attempt(self) -> Attempt:
        return self.attempts[-1]

    @property
    def answers(self) -> int:
        return sum(turn["role"] == "user" for turn in self.attempt.messages)


class PracticeStore:
    def __init__(self, *, ttl_seconds=3600, max_sessions=100, clock=time.monotonic):
        self.sessions: dict[str, Practice] = {}
        self.creations: dict[str, tuple[str, str]] = {}
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self.clock = clock

    def prune(self):
        now = self.clock()
        for key, practice in list(self.sessions.items()):
            if now - practice.touched >= self.ttl_seconds:
                practice.deleted = True
                practice.generation += 1
                if practice.inflight:
                    practice.inflight.cancel()
                del self.sessions[key]
        self.creations = {key: value for key, value in self.creations.items() if value[0] in self.sessions}

    def get(self, session_id: str) -> Practice:
        self.prune()
        if session_id not in self.sessions:
            raise AppError(404, "This practice expired or was reset. Reset the screen and start a new practice.", "PRACTICE_NOT_FOUND")
        practice = self.sessions[session_id]
        practice.touched = self.clock()
        return practice

    @staticmethod
    def snapshot(practice: Practice) -> dict:
        return {
            "sessionId": practice.session_id,
            "context": practice.context.model_dump(by_alias=True),
            "maxAnswers": MAX_ANSWERS,
            "pendingStage": practice.pending,
            "attempts": [{"number": attempt.number, "messages": copy.deepcopy(attempt.messages), "feedback": attempt.feedback.model_dump(by_alias=True) if attempt.feedback else None} for attempt in practice.attempts],
            "playback": copy.deepcopy(practice.attempt.playback),
        }

    @staticmethod
    def signature(operation: str, payload=None) -> str:
        return hashlib.sha256(json.dumps([operation, payload], sort_keys=True).encode()).hexdigest()

    def replayed(self, practice: Practice, request_id: str, operation: str, payload=None) -> bool:
        if request_id not in practice.requests:
            return False
        if practice.requests[request_id] != self.signature(operation, payload):
            raise AppError(409, "A request identifier was reused for a different action. Please retry the current step.", "REQUEST_CONFLICT")
        return True

    def remember(self, practice: Practice, request_id: str, operation: str, payload=None):
        practice.requests[request_id] = self.signature(operation, payload)
        if len(practice.requests) > 256:
            practice.requests.popitem(last=False)

    def create(self, context: Context, request_id: str) -> dict:
        self.prune()
        signature = self.signature("create", context.model_dump(by_alias=True))
        if request_id in self.creations:
            session_id, previous = self.creations[request_id]
            if signature != previous:
                raise AppError(409, "The creation request does not match the original scenario.", "REQUEST_CONFLICT")
            return self.snapshot(self.get(session_id))
        if len(self.sessions) >= self.max_sessions:
            raise AppError(503, "The local practice limit was reached. Reset an existing session and try again.", "SESSION_LIMIT")
        practice = Practice(secrets.token_urlsafe(24), context.model_copy(deep=True), touched=self.clock())
        self.sessions[practice.session_id] = practice
        self.creations[request_id] = (practice.session_id, signature)
        return self.snapshot(practice)

    @staticmethod
    def require_idle(practice: Practice):
        if practice.lock.locked():
            raise AppError(409, "Wait for this step, or stop it before starting another action.", "PRACTICE_BUSY")

    def answer(self, session_id: str, text: str, request_id: str) -> dict:
        practice = self.get(session_id)
        if self.replayed(practice, request_id, "answer", text):
            return self.snapshot(practice)
        self.require_idle(practice)
        if practice.pending or practice.attempt.feedback or not practice.attempt.messages or practice.attempt.messages[-1]["role"] != "assistant" or practice.answers >= MAX_ANSWERS:
            raise AppError(409, "Wait until it is your turn to answer.", "NOT_YOUR_TURN")
        practice.attempt.messages.append({"role": "user", "content": text})
        practice.pending = "coach" if practice.answers >= MAX_ANSWERS else "roleplay"
        self.remember(practice, request_id, "answer", text)
        return self.snapshot(practice)

    def finish(self, session_id: str, request_id: str) -> dict:
        practice = self.get(session_id)
        if self.replayed(practice, request_id, "finish"):
            return self.snapshot(practice)
        self.require_idle(practice)
        if not practice.answers or practice.attempt.feedback:
            raise AppError(400, "Give at least one answer before requesting new feedback.", "INVALID_INPUT")
        practice.pending = "coach"
        self.remember(practice, request_id, "finish")
        return self.snapshot(practice)

    def retry(self, session_id: str, request_id: str) -> dict:
        practice = self.get(session_id)
        if self.replayed(practice, request_id, "retry"):
            return self.snapshot(practice)
        self.require_idle(practice)
        if not practice.attempt.feedback:
            raise AppError(400, "Finish this practice before starting a second attempt.", "INVALID_INPUT")
        if len(practice.attempts) >= 10:
            raise AppError(409, "You have completed ten attempts. Reset to start a fresh practice.", "ATTEMPT_LIMIT")
        practice.attempts.append(Attempt(len(practice.attempts) + 1))
        practice.pending = "roleplay"
        self.remember(practice, request_id, "retry")
        return self.snapshot(practice)

    async def advance(self, session_id: str, request_id: str, provider) -> dict:
        practice = self.get(session_id)
        self.require_idle(practice)
        async with practice.lock:
            if self.replayed(practice, request_id, "advance"):
                return self.snapshot(practice)
            if not practice.pending:
                self.remember(practice, request_id, "advance")
                return self.snapshot(practice)
            generation = practice.generation
            stage = practice.pending
            history = copy.deepcopy(practice.attempt.messages)
            previous = copy.deepcopy(practice.attempts[-2].messages) if len(practice.attempts) > 1 else None
            task = asyncio.create_task(provider.roleplay(practice.context, history) if stage == "roleplay" else provider.coach(practice.context, history, previous))
            practice.inflight = task
            try:
                result = await task
                if practice.deleted or generation != practice.generation:
                    raise AppError(409, "This step was stopped. Continue when you are ready.", "STALE_REQUEST")
                if stage == "roleplay":
                    practice.attempt.messages.append({"role": "assistant", "content": result})
                    practice.attempt.playback = {"text": result, "speaker": "Project manager"}
                else:
                    practice.attempt.feedback = result
                    practice.attempt.playback = {"text": result.summary, "speaker": "Coach"}
                practice.pending = None
                practice.touched = self.clock()
                self.remember(practice, request_id, "advance")
                return self.snapshot(practice)
            finally:
                if not task.done():
                    task.cancel()
                if practice.inflight is task:
                    practice.inflight = None

    @staticmethod
    async def _cancel_inflight(practice: Practice):
        """Invalidate any running step and wait for its cancellation before reading or freeing state."""
        practice.generation += 1
        inflight = practice.inflight
        if inflight:
            inflight.cancel()
            await asyncio.gather(inflight, return_exceptions=True)

    async def stop(self, session_id: str) -> dict:
        practice = self.get(session_id)
        await self._cancel_inflight(practice)
        async with practice.lock:
            if practice.deleted:
                raise AppError(404, "This practice expired or was reset. Reset the screen and start a new practice.", "PRACTICE_NOT_FOUND")
            practice.touched = self.clock()
            return self.snapshot(practice)

    async def delete(self, session_id: str):
        practice = self.sessions.pop(session_id, None)
        if practice:
            practice.deleted = True
            await self._cancel_inflight(practice)
            async with practice.lock:
                pass
        self.prune()
