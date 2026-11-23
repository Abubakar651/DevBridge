from pathlib import Path
import subprocess

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_node_esm(script: str) -> None:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_recorder_vad_ignores_initial_silence_and_auto_finishes_after_post_speech_pause():
    run_node_esm("""
    import assert from 'node:assert/strict';
    import { Recorder } from './web/audio.js';

    let currentAmplitude = 0.002; // initial background silence
    let closedContexts = 0;
    let disconnectedSources = 0;

    class FakeAudioContext {
      constructor() { this.state = 'running'; }
      createMediaStreamSource() {
        return {
          connect() {},
          disconnect() { disconnectedSources++; },
        };
      }
      createAnalyser() {
        return {
          fftSize: 64,
          getFloatTimeDomainData(buffer) {
            buffer.fill(currentAmplitude);
          },
        };
      }
      async close() {
        this.state = 'closed';
        closedContexts++;
      }
    }

    class FakeMediaRecorder {
      static isTypeSupported() { return true; }
      constructor() { this.state = 'inactive'; this.mimeType = 'audio/webm'; }
      start() { this.state = 'recording'; }
      stop() {
        this.state = 'inactive';
        this.ondataavailable?.({ data: new Blob(['voice-data'], { type: 'audio/webm' }) });
        this.onstop?.();
      }
    }

    let stoppedTracks = 0;
    const stream = { getTracks: () => [{ stop() { stoppedTracks++; } }] };
    const rec = new Recorder({
      mediaDevices: { getUserMedia: async () => stream },
      RecorderClass: FakeMediaRecorder,
      AudioContextClass: FakeAudioContext,
      vadIntervalMs: 10,
      speechThreshold: 0.02,
      silenceThreshold: 0.012,
      minSpeechMs: 30,
      silenceDurationMs: 40,
    });

    let silenceTriggered = 0;
    const activities = [];
    await rec.start(
      () => {},
      () => {},
      {
        autoStopOnSilence: true,
        onSilence: () => { silenceTriggered++; },
        onActivity: info => { activities.push(info); },
      },
    );

    // 1. Pre-speech silence for 70ms must NOT trigger auto-stop.
    await new Promise(r => setTimeout(r, 70));
    assert.equal(silenceTriggered, 0);
    assert.equal(activities.some(a => a.speechDetected), false);

    // 2. Active speech above threshold for 45ms sets speechDetected = true.
    currentAmplitude = 0.08;
    await new Promise(r => setTimeout(r, 45));
    assert.equal(activities.some(a => a.speaking && a.speechDetected), true);
    assert.equal(silenceTriggered, 0);

    // 3. Post-speech silence for 65ms triggers onSilence exactly once.
    currentAmplitude = 0.001;
    await new Promise(r => setTimeout(r, 65));
    assert.equal(silenceTriggered, 1);

    const blob = await rec.finish();
    assert.ok(blob.size > 0);
    assert.equal(closedContexts, 1);
    assert.equal(disconnectedSources, 1);
    assert.equal(stoppedTracks, 1);
    """)


def test_practice_session_vad_auto_finishes_or_respects_manual_only_and_cleans_up_on_stop():
    run_node_esm("""
    import assert from 'node:assert/strict';
    import { Recorder } from './web/audio.js';
    import { PracticeSession } from './web/session.js';

    let currentAmplitude = 0.06;
    let closedContexts = 0;

    class FakeAudioContext {
      constructor() { this.state = 'running'; }
      createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
      createAnalyser() {
        return {
          fftSize: 32,
          getFloatTimeDomainData(buffer) { buffer.fill(currentAmplitude); },
        };
      }
      async close() { this.state = 'closed'; closedContexts++; }
    }

    class FakeMediaRecorder {
      static isTypeSupported() { return true; }
      constructor() { this.state = 'inactive'; this.mimeType = 'audio/webm'; }
      start() { this.state = 'recording'; }
      stop() {
        this.state = 'inactive';
        this.ondataavailable?.({ data: new Blob(['spoken-turn'], { type: 'audio/webm' }) });
        this.onstop?.();
      }
    }

    const stream = { getTracks: () => [{ stop() {} }] };
    const makeRecorder = () => new Recorder({
      mediaDevices: { getUserMedia: async () => stream },
      RecorderClass: FakeMediaRecorder,
      AudioContextClass: FakeAudioContext,
      vadIntervalMs: 10,
      speechThreshold: 0.02,
      silenceThreshold: 0.012,
      minSpeechMs: 20,
      silenceDurationMs: 30,
    });

    let transcribedCount = 0;
    const baseSnapshot = {
      sessionId: 'vad-s1',
      maxAnswers: 10,
      pendingStage: null,
      attempts: [{ number: 1, messages: [{ role: 'assistant', content: 'How is the rollout going?' }], feedback: null }],
    };
    const api = {
      async transcribe() {
        transcribedCount++;
        return { text: 'The model is tested and ready for a four-week CRM rollout.' };
      },
      async answer(id, text) {
        return {
          sessionId: id,
          maxAnswers: 10,
          pendingStage: 'roleplay',
          attempts: [{
            number: 1,
            messages: [
              { role: 'assistant', content: 'How is the rollout going?' },
              { role: 'user', content: text },
            ],
            feedback: null,
          }],
        };
      },
      async advance(id) {
        return {
          sessionId: id,
          maxAnswers: 10,
          pendingStage: null,
          attempts: [{
            number: 1,
            messages: [
              { role: 'assistant', content: 'How is the rollout going?' },
              { role: 'user', content: 'The model is tested and ready for a four-week CRM rollout.' },
              { role: 'assistant', content: 'What decision do you need today?' },
            ],
            feedback: null,
          }],
        };
      },
      async stop() {},
      async reset() {},
    };

    const session = new PracticeSession({ api, recorder: makeRecorder(), player: { stop() {}, play: async () => {} } });
    session.voiceEnabled = false;
    session.snapshot = structuredClone(baseSnapshot);

    // 1. With autoStopSilence = false (manual mode), post-speech silence does NOT auto-submit; manual finishRecording() works.
    session.setAutoStopSilence(false);
    assert.equal(session.autoStopSilence, false);
    currentAmplitude = 0.07;
    await session.startRecording();
    await new Promise(r => setTimeout(r, 35));
    assert.equal(session.voiceActivity.speechDetected, true);
    currentAmplitude = 0.001;
    await new Promise(r => setTimeout(r, 55));
    assert.equal(session.state, 'LISTENING');
    assert.equal(transcribedCount, 0);

    // Manual Done speaking button (finishRecording) completes the turn cleanly.
    await session.finishRecording();
    assert.equal(transcribedCount, 1);
    assert.equal(session.state, 'IDLE');
    assert.equal(session.voiceActivity.speaking, false);
    assert.equal(session.voiceActivity.speechDetected, false);

    // 2. With autoStopSilence = true (default), speech followed by silence auto-finishes and submits the turn.
    session.setAutoStopSilence(true);
    currentAmplitude = 0.07;
    await session.startRecording();
    await new Promise(r => setTimeout(r, 35));
    assert.equal(session.voiceActivity.speechDetected, true);
    currentAmplitude = 0.001;
    await new Promise(r => setTimeout(r, 65));
    // Wait briefly for async finishRecording -> transcribe -> answer -> advance to settle
    await new Promise(r => setTimeout(r, 30));
    assert.equal(transcribedCount, 2);
    assert.equal(session.state, 'IDLE');
    assert.equal(session.voiceActivity.speechDetected, false);

    // 3. Stopping mid-recording cleans up AudioContext and resets voiceActivity without submitting.
    currentAmplitude = 0.07;
    await session.startRecording();
    await new Promise(r => setTimeout(r, 25));
    session.stop();
    await new Promise(r => setTimeout(r, 50));
    assert.equal(session.state, 'IDLE');
    assert.equal(session.voiceActivity.speaking, false);
    assert.equal(session.voiceActivity.speechDetected, false);
    assert.equal(transcribedCount, 2);
    assert.ok(closedContexts >= 3);
    """)
