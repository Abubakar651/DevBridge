import json
from pathlib import Path
import subprocess

import httpx
import pytest

from server.app import create_app
from server.config import Settings
from server.providers import Providers
from server.scenario import DEFAULT_CONTEXT
from tests.test_phase3_slice1 import TEST_SETTINGS, gemini_json_response

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_ten_repeated_vad_silence_retry_stop_and_reset_cycles_without_loops_or_duplicates():
    script = """
    import assert from 'node:assert/strict';
    import { Recorder, SpeechPlayer } from './web/audio.js';
    import { PracticeSession } from './web/session.js';

    let currentAmplitude = 0.08;
    let openedContexts = 0;
    let closedContexts = 0;

    class FakeAudioContext {
      constructor() { this.state = 'running'; openedContexts++; }
      createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
      createAnalyser() {
        return {
          fftSize: 32,
          getFloatTimeDomainData(buffer) { buffer.fill(currentAmplitude); },
        };
      }
      async close() {
        if (this.state !== 'closed') {
          this.state = 'closed';
          closedContexts++;
        }
      }
    }

    class FakeMediaRecorder {
      static isTypeSupported() { return true; }
      constructor() { this.state = 'inactive'; this.mimeType = 'audio/webm'; }
      start() { this.state = 'recording'; }
      stop() {
        this.state = 'inactive';
        this.ondataavailable?.({ data: new Blob(['cycle-audio'], { type: 'audio/webm' }) });
        this.onstop?.();
      }
    }

    const stream = { getTracks: () => [{ stop() {} }] };
    const recorder = new Recorder({
      mediaDevices: { getUserMedia: async () => stream },
      RecorderClass: FakeMediaRecorder,
      AudioContextClass: FakeAudioContext,
      vadIntervalMs: 8,
      speechThreshold: 0.02,
      silenceThreshold: 0.012,
      minSpeechMs: 16,
      silenceDurationMs: 24,
    });

    let speakCalls = 0;
    let answerCalls = 0;
    const player = new SpeechPlayer(
      async () => { speakCalls++; return new Blob(['RIFFxxxxWAVEfmt ']); },
      {
        segmentText: async text => [text],
        createAudio: () => ({
          play() { queueMicrotask(() => this.onended?.()); return Promise.resolve(); },
          pause() {},
        }),
        createUrl: () => 'blob:mock',
        revokeUrl: () => {},
        guardMs: 5,
      },
    );

    let messages = [];
    let attemptNum = 1;
    const api = {
      async create(context) {
        attemptNum = 1;
        messages = [];
        return { sessionId: 'stress-session', maxAnswers: 10, context, pendingStage: 'roleplay', attempts: [{ number: 1, messages: [...messages], feedback: null }] };
      },
      async advance(id) {
        if (!messages.length || messages.at(-1).role === 'user') {
          messages.push({ role: 'assistant', content: `Question ${messages.length + 1}?` });
          return {
            sessionId: id,
            maxAnswers: 10,
            pendingStage: null,
            playback: { text: messages.at(-1).content, speaker: 'Stakeholder' },
            attempts: [{ number: attemptNum, messages: [...messages], feedback: null }],
          };
        }
        return {
          sessionId: id,
          maxAnswers: 10,
          pendingStage: null,
          attempts: [{
            number: attemptNum,
            messages: [...messages],
            feedback: {
              strength: { title: 'Clear', quote: messages[1].content, reason: 'Direct.' },
              improvements: [{ dimension: 'Assertiveness', quote: messages[1].content, reason: 'Add ask.', suggestion: 'Ask for approval.' }],
              improvedMessage: 'We organized the data and recommend approving the four-week rollout.',
              summary: 'Good progress.',
              retryFocus: 'Ask clearly.',
              missingFacts: [],
              comparison: attemptNum > 1 ? 'Improved assertiveness on the checklist.' : '',
            },
          }],
        };
      },
      async transcribe() {
        return { text: `Spoken answer ${answerCalls + 1}` };
      },
      async answer(id, text) {
        answerCalls++;
        messages.push({ role: 'user', content: text });
        return {
          sessionId: id,
          maxAnswers: 10,
          pendingStage: 'roleplay',
          attempts: [{ number: attemptNum, messages: [...messages], feedback: null }],
        };
      },
      async finish(id) {
        return { sessionId: id, maxAnswers: 10, pendingStage: 'coach', attempts: [{ number: attemptNum, messages: [...messages], feedback: null }] };
      },
      async retry(id) {
        attemptNum++;
        messages = [];
        return { sessionId: id, maxAnswers: 10, pendingStage: 'roleplay', attempts: [{ number: attemptNum, messages: [], feedback: null }] };
      },
      async stop() {},
      async reset() {},
    };

    const session = new PracticeSession({ api, recorder, player });
    await session. start({ scenarioId: 'churn-pitch', difficulty: 'skeptical' });

    for (let cycle = 0; cycle < 10; cycle++) {
      // Speak -> auto-silence finishes recording and submits exactly one answer
      currentAmplitude = 0.08;
      await session.startRecording();
      await new Promise(r => setTimeout(r, 25));
      currentAmplitude = 0.001;
      await new Promise(r => setTimeout(r, 55));

      // Wait for transcribe -> answer -> advance -> playback to settle
      for (let wait = 0; wait < 25 && session.busy; wait++) {
        await new Promise(r => setTimeout(r, 10));
      }
      assert.equal(session.state, 'IDLE');
      const userTurns = session.attempt.messages.filter(m => m.role === 'user');
      assert.equal(userTurns.length, 1, `Expected 1 user turn in cycle ${cycle}, got ${userTurns.length}`);

      if (cycle % 2 === 0) {
        // Test mid-recording Stop followed by Finish & Retry
        currentAmplitude = 0.08;
        await session.startRecording();
        await new Promise(r => setTimeout(r, 15));
        session.stop();
        assert.equal(session.state, 'IDLE');
        await session.finish();
        assert.ok(session.feedback);
        await session.retry();
      } else {
        // Test full Reset and fresh Start
        session.reset();
        assert.equal(session.snapshot, null);
        await session.start({ scenarioId: 'churn-pitch', difficulty: 'supportive' });
      }
    }

    session.reset();
    assert.equal(answerCalls, 10);
    assert.equal(openedContexts, closedContexts);
    """
    result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=PROJECT_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.anyio
async def test_difficulty_and_checklist_comparison_across_two_attempts_end_to_end():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        body = json.loads(request.content.decode("utf-8"))
        payload = json.loads(body["input"])
        if "history" in payload:
            return gemini_json_response({"reply": "What is the rollout plan and decision needed?", "closed": False})
        is_retry = payload.get("previousAttempt") is not None
        return gemini_json_response({
            "strength": {
                "title": "Clear progress",
                "quote": "We spent the first four weeks organizing historical customer data",
                "reason": "Grounded opening.",
            },
            "improvements": [
                {
                    "dimension": "Assertiveness" if not is_retry else "Accuracy and next steps",
                    "quote": "Integrating automated at-risk alerts into the CRM requires four additional working weeks.",
                    "reason": "Needs explicit approval question.",
                    "suggestion": "Ask directly to approve the four-week CRM phase.",
                }
            ],
            "improvedMessage": "We spent the first four weeks organizing historical customer data and building a churn prediction model. Integrating automated at-risk alerts into the CRM requires four additional working weeks. I recommend approving the four-week CRM integration phase.",
            "summary": "Solid structure; keep the approval question explicit.",
            "retryFocus": "Ask for rollout approval.",
            "missingFacts": [],
            "comparison": "On the 5-dimension communication checklist, Assertiveness improved while Accuracy and next steps remains the focus." if is_retry else "",
        })

    transport = httpx.MockTransport(handler)
    settings = Settings(**{**TEST_SETTINGS.__dict__, "gemini_key": "test-gemini-key"})
    app = create_app(
        settings_loader=lambda: settings,
        provider_factory=lambda s: Providers(s, transport=transport),
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:4317") as client:
        created = await client.post(
            "/api/practice",
            json={"context": {**DEFAULT_CONTEXT, "difficulty": "supportive"}, "requestId": "p3-s4-create-0001"},
        )
        assert created.status_code == 200
        sid = created.json()["sessionId"]

        await client.post(f"/api/practice/{sid}/advance", json={"requestId": "p3-s4-open-00001"})
        await client.post(
            f"/api/practice/{sid}/answer",
            json={
                "text": "We spent the first four weeks organizing historical customer data. Integrating automated at-risk alerts into the CRM requires four additional working weeks.",
                "requestId": "p3-s4-ans-000001",
            },
        )
        await client.post(f"/api/practice/{sid}/finish", json={"requestId": "p3-s4-fin-000001"})
        first_coach = await client.post(f"/api/practice/{sid}/advance", json={"requestId": "p3-s4-coach-0001"})
        assert first_coach.status_code == 200
        assert first_coach.json()["attempts"][0]["feedback"]["comparison"] == ""

        retried = await client.post(f"/api/practice/{sid}/retry", json={"requestId": "p3-s4-retry-0001"})
        assert retried.status_code == 200
        await client.post(f"/api/practice/{sid}/advance", json={"requestId": "p3-s4-open-00002"})
        await client.post(
            f"/api/practice/{sid}/answer",
            json={
                "text": "We spent the first four weeks organizing historical customer data. Integrating automated at-risk alerts into the CRM requires four additional working weeks.",
                "requestId": "p3-s4-ans-000002",
            },
        )
        await client.post(f"/api/practice/{sid}/finish", json={"requestId": "p3-s4-fin-000002"})
        second_coach = await client.post(f"/api/practice/{sid}/advance", json={"requestId": "p3-s4-coach-0002"})
        assert second_coach.status_code == 200
        second_feedback = second_coach.json()["attempts"][1]["feedback"]
        assert "5-dimension communication checklist" in second_feedback["comparison"]


def test_phase3_pilot_validation_report_and_agents_md_documented():
    report = source("docs/PHASE_3_PILOT_VALIDATION.md")
    agents = source("agents.md")

    assert "Phase 3 Qualitative Pilot & Completion Gate Validation" in report
    assert "does not promise a guaranteed workplace reaction" in report
    assert "L1 — AI/ML Engineer" in report
    assert "Reviewer 3 (HR lens)" in report

    assert "DIFFICULTIES" in agents
    assert "CHECKLIST_DIMENSIONS" in agents
    assert "auto-silence" in agents
    assert "DEV-31" in agents
