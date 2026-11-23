import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_header_scenario_pill_and_empty_scene_button_are_accessible_triggers():
    html = source("web/index.html")
    css = source("web/styles.css")
    app = source("web/app.js")

    pill_match = re.search(r'<button\b[^>]*id="header-scenario-pill"[^>]*>', html)
    assert pill_match, "Expected #header-scenario-pill to be a <button>"
    pill_tag = pill_match.group(0)
    assert 'type="button"' in pill_tag
    assert 'aria-controls="context-panel"' in pill_tag
    assert 'aria-expanded="false"' in pill_tag

    empty_section = html[html.index('id="empty-conversation"'):html.index('id="messages"')]
    assert 'id="empty-scene-button"' in empty_section
    assert 'type="button"' in empty_section
    assert 'Switch scenario or stakeholder' in empty_section

    assert ".header-scenario-pill:hover" in css
    assert ".empty-scene-link" in css

    assert "$('header-scenario-pill')?.addEventListener('click', () => setSceneOpen(!sceneOpen));" in app
    assert "$('empty-scene-button')?.addEventListener('click', () => { setSceneOpen(true); setBriefMode('edit'); $('scenario')?.focus(); });" in app
    assert "$('header-scenario-pill').setAttribute('aria-expanded', sceneOpen ? 'true' : 'false');" in app


def test_retry_and_reset_collapse_coaching_drawer_to_recenter_workspace():
    app = source("web/app.js")
    assert "$('reset-button').addEventListener('click', () => { setCoachOpen(false);" in app
    assert "$('retry-button').addEventListener('click', () => { setCoachOpen(false);" in app


def test_custom_mix_badge_and_dynamic_scene_description():
    html = source("web/index.html")
    css = source("web/styles.css")
    app = source("web/app.js")
    assert 'id="scenario-custom-badge"' in html
    assert 'class="scenario-custom-badge"' in html
    assert ".scenario-custom-badge" in css
    assert "isContextCustomized" in app
    assert "scenario-custom-badge" in app
    assert "Custom mix" in app
    assert "Custom audience: practising" in app


def test_coach_prompt_covers_early_finish_and_strict_numeric_grounding():
    prompts = source("server/prompts.py")
    assert "Even when the learner finishes early after one or two answers" in prompts
    assert "never complain that the conversation ended early" in prompts
    assert "do NOT introduce any digits or number words" in prompts
    assert "never turn a work-effort duration into a delivery window" in prompts


def test_voice_enabled_sync_and_closing_speech_mute_advances_to_coach():
    app = source("web/app.js")
    assert "const speechConfigured = Boolean(configuration?.configured.speech);" in app
    assert "$('voice-enabled').checked = configuration ? Boolean(state.voiceEnabled && speechConfigured) : state.voiceEnabled;" in app
    assert "const enabled = Boolean(event.target.checked && configuration?.configured.speech);" in app

    script = """
    import assert from 'node:assert/strict';
    import { PracticeSession } from './web/session.js';

    let advanceCalls = 0;
    let playAborted = false;
    const feedback = {
      strength: { title: 'Clear', quote: 'We recommend', reason: 'Direct.' },
      improvements: [{ dimension: 'Audience clarity', quote: 'We recommend', reason: 'Short.', suggestion: 'Add context.' }],
      improvedMessage: 'We recommend approving the four-week plan.',
      summary: 'Good start.',
      retryFocus: 'Add one clear detail.',
      missingFacts: [],
      comparison: '',
    };
    const api = {
      async finish(id) {
        return { sessionId: id, maxAnswers: 10, pendingStage: 'coach', attempts: [{ number: 1, messages: [{ role: 'user', content: 'We recommend this.' }], feedback: null }] };
      },
      async advance(id) {
        advanceCalls++;
        if (advanceCalls === 1) {
          return {
            sessionId: id,
            maxAnswers: 10,
            pendingStage: 'coach',
            playback: { text: 'Thank you, that works.', speaker: 'VP of Operations' },
            attempts: [{ number: 1, messages: [{ role: 'user', content: 'We recommend this.' }], feedback: null }],
          };
        }
        return {
          sessionId: id,
          maxAnswers: 10,
          pendingStage: null,
          attempts: [{ number: 1, messages: [{ role: 'user', content: 'We recommend this.' }], feedback }],
        };
      },
    };
    let resolveSpeakingStarted;
    const speakingStarted = new Promise(resolve => { resolveSpeakingStarted = resolve; });
    const player = {
      stop() {},
      play(_text, { signal, onState }) {
        onState?.('SPEAKING');
        resolveSpeakingStarted();
        return new Promise((_resolve, reject) => {
          signal.addEventListener('abort', () => {
            playAborted = true;
            reject(new DOMException('Cancelled', 'AbortError'));
          }, { once: true });
        });
      },
    };
    const session = new PracticeSession({ api, recorder: { supported: true, cancel() {} }, player });
    session.snapshot = {
      sessionId: 's1',
      maxAnswers: 10,
      pendingStage: null,
      attempts: [{ number: 1, messages: [{ role: 'user', content: 'We recommend this.' }], feedback: null }],
    };

    const finishPromise = session.finish();
    await speakingStarted;
    await session.setVoiceEnabled(false);
    await finishPromise;

    assert.equal(playAborted, true);
    assert.equal(advanceCalls, 2);
    assert.equal(session.voiceEnabled, false);
    assert.equal(session.feedback?.summary, 'Good start.');
    assert.equal(session.state, 'IDLE');
    """
    result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=PROJECT_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_recorder_cancel_avoids_double_stop_and_sync_onstop_race():
    script = """
    import assert from 'node:assert/strict';
    import { Recorder } from './web/audio.js';

    // 1. Cancelling a pending finish() stops the underlying recorder once during cancel and rejects with AbortError even if stop() fires onstop synchronously.
    {
      let stopCalls = 0;
      let stoppedTracks = 0;
      class SyncOnCancelRecorder {
        static isTypeSupported() { return true; }
        constructor() { this.state = 'inactive'; this.mimeType = 'audio/webm'; }
        start() { this.state = 'recording'; }
        stop() {
          stopCalls++;
          if (stopCalls === 1) {
            this.state = 'stopping';
            return;
          }
          this.state = 'inactive';
          this.onstop?.();
        }
      }
      const stream = { getTracks: () => [{ stop() { stoppedTracks++; } }] };
      const rec = new Recorder({ mediaDevices: { getUserMedia: async () => stream }, RecorderClass: SyncOnCancelRecorder });
      await rec.start(() => {});
      const pending = rec.finish();
      assert.equal(stopCalls, 1);
      rec.cancel();
      assert.equal(stopCalls, 2);
      await assert.rejects(() => pending, err => err.name === 'AbortError');
      assert.equal(stoppedTracks, 1);
      assert.equal(rec.recorder, null);
    }

    // 2. Aborting via AbortSignal inside finish() detaches onstop before stop() so synchronous onstop cannot resolve a Blob.
    {
      let stoppedTracks = 0;
      class ImmediateStopRecorder {
        static isTypeSupported() { return true; }
        constructor() { this.state = 'inactive'; this.mimeType = 'audio/webm'; }
        start() { this.state = 'recording'; }
        stop() {
          if (this.state === 'stopping') {
            this.state = 'inactive';
            this.onstop?.();
            return;
          }
          this.state = 'stopping';
        }
      }
      const stream = { getTracks: () => [{ stop() { stoppedTracks++; } }] };
      const rec = new Recorder({ mediaDevices: { getUserMedia: async () => stream }, RecorderClass: ImmediateStopRecorder });
      await rec.start(() => {});
      const ac = new AbortController();
      const pending = rec.finish(ac.signal);
      ac.abort();
      await assert.rejects(() => pending, err => err.name === 'AbortError');
      assert.equal(stoppedTracks, 1);
      assert.equal(rec.recorder, null);
    }
    """
    result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=PROJECT_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_mobile_header_unsticky_and_stakeholder_prose_casing():
    css = source("web/styles.css")
    app = source("web/app.js")
    mobile_section = css[css.index("@media (max-width: 700px)"):]
    assert ".site-header { position: static;" in mobile_section
    assert "function stakeholderProse(label)" in app
    assert "$('partner-name').textContent = coaching ? 'Your communication coach' : `Your ${stakeholderProse(stakeholder)}`;" in app
    assert "$('composer-prompt-label').textContent = `Message your ${stakeholderProse(" in app
    assert "with your ${stakeholderProse(persona.label)}.`" in app


def test_mobile_only_isolated_collapsible_quick_starters():
    html = source("web/index.html")
    css = source("web/styles.css")
    app = source("web/app.js")

    toggle_match = re.search(r'<button\b[^>]*id="starter-mobile-toggle"[^>]*>', html)
    assert toggle_match, "Expected #starter-mobile-toggle in web/index.html"
    assert 'type="button"' in toggle_match.group(0)
    assert 'aria-controls="starter-chips"' in toggle_match.group(0)
    assert 'data-mobile-open="false"' in html

    desktop_section = css[:css.index("@media (max-width: 700px)")]
    mobile_section = css[css.index("@media (max-width: 700px)"):]
    assert ".starter-mobile-toggle { display: none; }" in desktop_section
    assert ".practice-controls > .starter-bar { order: 4;" in mobile_section
    assert '.starter-bar[data-mobile-open="false"] .starter-chips { display: none; }' in mobile_section

    assert "function setMobileStartersOpen(open)" in app
    assert "setMobileStartersOpen(false);" in app




