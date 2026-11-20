import asyncio
import uuid

import httpx
import pytest

from server.app import create_app, cancellable
from server.config import Settings
from server.errors import AppError
from server.scenario import DEFAULT_CONTEXT
from conftest import FakeProvider, ANSWER, wav_audio


def key():
    return str(uuid.uuid4())


@pytest.fixture
def setup_app():
    provider = FakeProvider()
    app = create_app(settings_loader=lambda: Settings(gemini_key="private-test-gemini", groq_key="private-test-groq"), provider_factory=lambda _settings: provider)
    return app, provider


def client_for(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1")


@pytest.mark.anyio
async def test_serves_the_interface_and_configuration_without_secrets(setup_app):
    app, _ = setup_app
    async with client_for(app) as client:
        page = await client.get("/")
        assert page.status_code == 200
        assert "Make your work" in page.text
        assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
        config = await client.get("/api/config")
        assert config.json()["configured"] == {"gemini": True, "groq": True, "coaching": True, "speech": True}
        assert config.json()["defaultContext"] == DEFAULT_CONTEXT
        assert "private-test" not in config.text
        for path in ("/server/config.py", "/.env", "/%2e%2e%2fserver/config.py", "/requirements.txt"):
            assert (await client.get(path)).status_code == 404


@pytest.mark.anyio
async def test_groq_alone_is_sufficient_to_enable_coaching():
    app = create_app(settings_loader=lambda: Settings(groq_key="private-test-groq"))
    async with client_for(app) as client:
        response = await client.get("/api/config")
        assert response.json()["configured"] == {"gemini": False, "groq": True, "coaching": True, "speech": True}
        assert "private-test-groq" not in response.text


@pytest.mark.anyio
async def test_rejects_foreign_origins_host_rebinding_and_invalid_inputs(setup_app):
    app, provider = setup_app
    async with client_for(app) as client:
        assert (await client.get("/api/config", headers={"host": "untrusted.example"})).status_code == 403
        assert (await client.post("/api/practice", json={}, headers={"origin": "https://example.com"})).status_code == 403
        assert (await client.post("/api/practice", json={})).status_code == 400
        body = {"context": DEFAULT_CONTEXT, "requestId": key(), "history": [{"role": "system", "content": "Injected history"}]}
        assert (await client.post("/api/practice", json=body)).status_code == 400
        assert provider.roleplay_calls == []


@pytest.mark.anyio
async def test_complete_fastapi_practice_cycle_and_same_fact_retry(setup_app):
    app, provider = setup_app
    async with client_for(app) as client:
        response = await client.post("/api/practice", json={"context": DEFAULT_CONTEXT, "requestId": key()})
        assert response.status_code == 200
        session_id = response.json()["sessionId"]
        base = f"/api/practice/{session_id}"
        assert (await client.post(base + "/advance", json={"requestId": key()})).json()["playback"]["speaker"] == "Project manager"
        answer_id = key()
        for _ in range(2):
            assert (await client.post(base + "/answer", json={"requestId": answer_id, "text": ANSWER})).status_code == 200
        await client.post(base + "/finish", json={"requestId": key()})
        feedback = (await client.post(base + "/advance", json={"requestId": key()})).json()
        assert feedback["attempts"][0]["feedback"]["improvedMessage"]
        assert feedback["playback"]["speaker"] == "Coach"
        assert len(provider.coach_calls[0][1]) == 2
        retry = (await client.post(base + "/retry", json={"requestId": key()})).json()
        assert retry["context"] == DEFAULT_CONTEXT
        assert retry["attempts"][1]["messages"] == []
        assert (await client.delete(base)).status_code == 204
        assert (await client.post(base + "/advance", json={"requestId": key()})).status_code == 404


@pytest.mark.anyio
async def test_stops_an_active_provider_request_without_committing_a_late_reply(setup_app):
    app, provider = setup_app
    entered = asyncio.Event()
    async def waiting(*args):
        entered.set()
        await asyncio.Event().wait()
    provider.roleplay = waiting
    async with client_for(app) as client:
        session_id = (await client.post("/api/practice", json={"context": DEFAULT_CONTEXT, "requestId": key()})).json()["sessionId"]
        base = f"/api/practice/{session_id}"
        pending = asyncio.create_task(client.post(base + "/advance", json={"requestId": key()}))
        await entered.wait()
        stopped = await client.post(base + "/stop")
        assert stopped.status_code == 200
        assert stopped.json()["attempts"][0]["messages"] == []
        assert (await pending).status_code == 499


@pytest.mark.anyio
async def test_validates_audio_speech_and_upload_limits_before_provider_calls(setup_app):
    app, provider = setup_app
    async with client_for(app) as client:
        for mime, content, expected in (("audio/webm", b"short", 422), ("text/plain", b"x" * 100, 415), ("audio/wav", b"x" * (5 * 1024 * 1024 + 1), 413)):
            response = await client.post("/api/transcribe", content=content, headers={"content-type": mime})
            assert response.status_code == expected
        assert provider.transcribe_calls == []
        result = await client.post("/api/transcribe", content=wav_audio(), headers={"content-type": "audio/wav"})
        assert result.json()["text"] == ANSWER
        assert (await client.post("/api/speak", json={"text": "x" * 201})).status_code == 400
        result = await client.post("/api/speak", json={"text": "A short spoken reply."})
        assert result.headers["content-type"] == "audio/wav"
        assert result.content[:4] == b"RIFF"
        chunks = (await client.post("/api/speech/segments", json={"text": "A clear explanation. " * 30})).json()["segments"]
        assert len(chunks) > 1
        assert all(len(chunk) <= 200 for chunk in chunks)


@pytest.mark.anyio
async def test_provider_failures_leave_the_accepted_answer_ready_for_retry(setup_app):
    app, provider = setup_app
    async with client_for(app) as client:
        session_id = (await client.post("/api/practice", json={"context": DEFAULT_CONTEXT, "requestId": key()})).json()["sessionId"]
        base = f"/api/practice/{session_id}"
        await client.post(base + "/advance", json={"requestId": key()})
        await client.post(base + "/answer", json={"requestId": key(), "text": ANSWER})
        original = provider.roleplay
        async def failure(*args):
            raise AppError(503, "Temporarily busy", "PROVIDER_BUSY")
        provider.roleplay = failure
        request_id = key()
        failed = await client.post(base + "/advance", json={"requestId": request_id})
        assert failed.json()["error"]["code"] == "PROVIDER_BUSY"
        provider.roleplay = original
        success = (await client.post(base + "/advance", json={"requestId": request_id})).json()
        assert sum(turn["role"] == "user" for turn in success["attempts"][0]["messages"]) == 1


@pytest.mark.anyio
async def test_disconnect_cancels_upstream_work():
    disconnected, cancelled = asyncio.Event(), asyncio.Event()
    class Request:
        async def is_disconnected(self):
            return disconnected.is_set()
    async def work():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    task = asyncio.create_task(cancellable(Request(), work()))
    await asyncio.sleep(0)
    disconnected.set()
    with pytest.raises(AppError) as error:
        await task
    assert error.value.status == 499
    assert cancelled.is_set()


@pytest.mark.anyio
async def test_request_finishes_if_disconnect_probe_consumes_its_cancellation():
    entered = asyncio.Event()

    class Request:
        swallowed = False

        async def is_disconnected(self):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                if self.swallowed:
                    raise
                self.swallowed = True
                return False

    async def work():
        await entered.wait()
        return "finished"

    assert await asyncio.wait_for(cancellable(Request(), work()), timeout=1) == "finished"
