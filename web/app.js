import { api } from './api.js';
import { Recorder, SpeechPlayer } from './audio.js';
import { PracticeSession } from './session.js';

const $ = id => document.getElementById(id);
const recorder = new Recorder();
const player = new SpeechPlayer(api.speak, { segmentText: api.segments });
const session = new PracticeSession({ api, recorder, player });
const supportsFieldSizing = typeof CSS !== 'undefined' && CSS.supports?.('field-sizing', 'content');
let configuration = null;
let messageSignature = '';
let feedbackSignature = '';
let errorSignature = '';
let configError = '';
let contextInitialized = false;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function paragraph(parent, className, text) { parent.append(element('p', className, text)); }
function autoResize(field, maxPx = 220) {
  if (supportsFieldSizing || !field) return;
  field.style.height = 'auto';
  field.style.height = `${Math.min(field.scrollHeight, maxPx)}px`;
}

function renderMessages(state) {
  const messages = state.attempt?.messages || [];
  const signature = JSON.stringify([state.attempt?.number, messages]);
  if (signature === messageSignature) return;
  messageSignature = signature;
  $('messages').replaceChildren();
  for (const message of messages) {
    const item = element('li', `message ${message.role}`);
    item.append(element('div', 'message-label', message.role === 'user' ? 'YOU' : 'PROJECT MANAGER'));
    paragraph(item, '', message.content);
    $('messages').append(item);
  }
  $('messages').hidden = !messages.length;
  $('empty-conversation').hidden = Boolean(messages.length);
  $('conversation-area').scrollTop = $('conversation-area').scrollHeight;
}

function renderFeedback(state) {
  const feedback = state.feedback;
  const signature = JSON.stringify([state.attempt?.number, feedback]);
  if (signature === feedbackSignature) return;
  feedbackSignature = signature;
  $('feedback').replaceChildren();
  $('feedback').hidden = !feedback;
  $('coach-placeholder').hidden = Boolean(feedback);
  $('feedback-actions').hidden = !feedback;
  if (!feedback) return;
  const strength = element('section', 'feedback-section');
  paragraph(strength, 'feedback-kicker', 'WHAT WORKED');
  strength.append(element('h3', 'feedback-title', feedback.strength.title));
  paragraph(strength, 'evidence', `“${feedback.strength.quote}”`);
  paragraph(strength, '', feedback.strength.reason);
  $('feedback').append(strength);
  for (const item of feedback.improvements) {
    const section = element('section', 'feedback-section improvement');
    paragraph(section, 'feedback-kicker', item.dimension.toUpperCase());
    paragraph(section, 'evidence', `“${item.quote}”`);
    paragraph(section, '', item.reason);
    paragraph(section, '', item.suggestion);
    $('feedback').append(section);
  }
  const rewrite = element('section', 'feedback-section');
  paragraph(rewrite, 'feedback-kicker', 'ONE WAY TO SAY IT');
  const box = element('div', 'rewrite'); paragraph(box, '', feedback.improvedMessage);
  rewrite.append(box); $('feedback').append(rewrite);
  if (feedback.missingFacts.length) {
    const missing = element('section', 'feedback-section missing-facts');
    paragraph(missing, 'feedback-kicker', 'WORTH CLARIFYING');
    for (const fact of feedback.missingFacts) paragraph(missing, '', fact);
    $('feedback').append(missing);
  }
  const focus = element('section', 'feedback-section');
  paragraph(focus, 'feedback-kicker', 'YOUR NEXT ATTEMPT'); paragraph(focus, '', feedback.retryFocus);
  $('feedback').append(focus);
}

function renderComparison(state) {
  $('comparison').hidden = state.attempts.length < 2;
  if (state.attempts.length < 2) return;
  const previous = state.attempts.at(-2);
  const current = state.attempt;
  const body = element('div', 'comparison-body');
  paragraph(body, '', current.feedback?.comparison || `Your focus: ${previous.feedback.retryFocus}`);
  const columns = element('div', 'comparison-columns');
  for (const attempt of [previous, current]) {
    const column = element('div', '');
    column.append(element('h3', '', `ATTEMPT ${attempt.number} · YOUR WORDS`));
    paragraph(column, '', attempt.messages.filter(item => item.role === 'user').map(item => item.content).join('\n\n') || 'Your next explanation will appear here.');
    columns.append(column);
  }
  body.append(columns); $('comparison-content').replaceChildren(body);
}

function stateLabel(state) {
  if (state.state === 'LISTENING') return state.recordReady ? 'Listening. Say it in your own words.' : 'Waiting for microphone permission…';
  if (state.state === 'TRANSCRIBING') return 'Turning your answer into text…';
  if (state.state === 'THINKING') return state.serverStage === 'coach' ? 'Your coach is reflecting on the conversation…' : 'Your project manager is thinking…';
  if (state.state === 'SYNTHESIZING') return 'Preparing the spoken reply…';
  if (state.state === 'SPEAKING') return state.blocked ? 'Your browser needs a tap to play audio.' : `${state.pending?.speaker || 'Your coach'} is speaking…`;
  if (state.state === 'ERROR') return state.answers ? 'Your accepted answers are still here.' : 'Nothing was submitted. Review the details and try again.';
  if (state.pending) return 'Paused. Continue when you’re ready.';
  if (state.feedback) return 'Your coaching notes are ready.';
  if (state.canAnswer) return state.voiceError ? 'Your turn (spoken audio paused — type or speak below).' : 'Your turn. Take your time.';
  return 'Ready when you are';
}

function render(state) {
  document.body.dataset.state = state.state;
  $('practice').setAttribute('aria-busy', state.busy ? 'true' : 'false');
  const active = Boolean(state.attempt);
  const coaching = Boolean(state.feedback) || state.serverStage === 'coach';
  const canCoachStart = Boolean(configuration?.configured.coaching);
  $('state-label').textContent = stateLabel(state);
  $('turn-count').textContent = `${state.answers} / ${configuration?.maxAnswers || 3} answers`;
  $('attempt-label').textContent = active ? `ATTEMPT ${state.attempt.number}` : 'FIRST ATTEMPT';
  $('partner-name').textContent = coaching ? 'Your communication coach' : 'Your project manager';
  $('partner-description').textContent = coaching ? 'Specific feedback, with your facts intact' : 'A simulated workplace conversation';
  $('partner-avatar').textContent = coaching ? 'VC' : 'PM';
  $('mode-badge').textContent = coaching ? 'COACHING' : 'ROLE-PLAY';
  $('start-button').hidden = active;
  $('start-button').disabled = !canCoachStart;
  $('record-button').hidden = !active || Boolean(state.feedback) || state.state === 'LISTENING';
  $('record-button').disabled = !state.canAnswer || !configuration?.configured.groq || !recorder.supported;
  $('done-button').hidden = state.state !== 'LISTENING';
  $('done-button').disabled = !state.recordReady;
  $('play-button').hidden = !state.blocked;
  $('continue-button').hidden = !state.pending || state.busy || state.state === 'ERROR';
  $('finish-button').hidden = !active || Boolean(state.feedback);
  $('finish-button').disabled = state.busy || !state.answers;
  $('stop-button').disabled = !active && !state.busy;
  $('reset-button').disabled = !active;
  $('mic-status').textContent = state.state === 'LISTENING' && state.recordReady ? 'Recording · up to 60 seconds' : 'Your microphone is off';
  $('voice-enabled').disabled = !configuration?.configured.speech;
  $('voice-enabled').checked = state.voiceEnabled;
  $('voice-notice').hidden = !state.voiceError;
  $('voice-notice-message').textContent = state.voiceError?.message || '';
  $('retry-voice-button').disabled = state.busy;
  $('type-answer').hidden = Boolean(state.feedback);
  $('answer-text').disabled = !state.canType || (!active && !canCoachStart);
  $('send-button').disabled = !state.canSend || (!active && !canCoachStart) || !$('answer-text').value.trim();
  $('answer-hint').textContent = !canCoachStart
    ? 'Connect Gemini or Groq in Practice setup to chat.'
    : !active
      ? 'Write an update and press Send to begin, or click Start practice above.'
      : state.canSend
        ? (state.state === 'SPEAKING' || state.state === 'SYNTHESIZING' ? 'Your words. Sending interrupts audio.' : 'Your words. No perfect script needed.')
        : (state.pending && !state.busy ? 'Practice paused — click Continue practice above before sending.' : 'Wait until the current step finishes.');
  $('starter-bar').hidden = !active || Boolean(state.feedback);
  for (const chip of document.querySelectorAll('.starter-chip')) chip.disabled = !state.canSend;
  $('retry-button').disabled = state.busy;
  $('hear-example').disabled = state.busy || !state.voiceEnabled || !configuration?.configured.speech;
  $('error-panel').hidden = !state.error;
  $('error-message').textContent = state.error?.message || '';
  const nextErrorSignature = state.error ? `${state.error.code || ''}:${state.error.message || ''}` : '';
  if (nextErrorSignature && nextErrorSignature !== errorSignature) queueMicrotask(() => $('error-panel').focus());
  errorSignature = nextErrorSignature;
  const recoveryType = state.pending?.type;
  $('recover-button').textContent = recoveryType === 'advance'
    ? (state.serverStage === 'coach' ? 'Try feedback again' : 'Retry response')
    : ({ speak: 'Retry playback', transcribe: 'Retry transcription' })[recoveryType] || 'Continue practice';
  for (const input of $('context-form').elements) input.disabled = active;
  $('context-note').textContent = active ? 'Retry keeps the same facts. Reset to change the scene.' : 'Your coach will use these facts. Keep them specific.';
  renderMessages(state); renderFeedback(state); renderComparison(state);
}

async function refreshConfiguration() {
  $('refresh-config').disabled = true;
  try {
    configuration = await api.config(); configError = '';
    if (!contextInitialized) {
      for (const key of ['discipline', 'knownFacts', 'goal', 'familiarity']) $(key === 'knownFacts' ? 'facts' : key).value = configuration.defaultContext[key];
      contextInitialized = true;
      autoResize($('facts'), 280);
      autoResize($('goal'), 180);
    }
    $('gemini-status').textContent = configuration.configured.gemini ? 'Key found' : 'Key missing';
    $('groq-status').textContent = configuration.configured.groq ? 'Key found' : configuration.configured.speech ? 'Output key found' : 'Key missing';
    $('test-notice').hidden = configuration.mode === 'live';
    if (!configuration.configured.speech) await session.setVoiceEnabled(false);
  } catch { configError = 'The local server is unavailable. Start it and check configuration again.'; }
  $('configuration-notice').hidden = !configError && Boolean(configuration?.configured.coaching && configuration?.configured.groq && configuration?.configured.speech);
  $('configuration-message').textContent = configError || (!configuration?.configured.coaching ? 'Connect Gemini or Groq to start your practice conversation. Your scenario is ready below.' : !configuration?.configured.groq ? 'Voice input is not configured yet. You can practise by typing.' : 'Spoken replies are not configured yet. Switch them off to continue practice.');
  $('refresh-config').disabled = false;
  render(session);
}

const contextChecks = [
  [$('facts'), 20, 'Add at least 20 visible characters describing what is known.'],
  [$('goal'), 10, 'Add at least 10 visible characters describing what you want to communicate.'],
];
function updateContextValidity() {
  for (const [input, minimum, message] of contextChecks) input.setCustomValidity(input.value.trim().length < minimum ? message : '');
}
function validateContext() {
  updateContextValidity();
  return $('context-form').reportValidity();
}
function readContext() {
  return { scenarioId: configuration.scenario.id, discipline: $('discipline').value, knownFacts: $('facts').value.trim(), goal: $('goal').value.trim(), familiarity: $('familiarity').value };
}
for (const [input] of contextChecks) input.addEventListener('input', () => { updateContextValidity(); autoResize(input, 280); });

$('start-button').addEventListener('click', () => {
  if (!validateContext()) return;
  session.start(readContext());
});
$('reset-scene-button').addEventListener('click', () => {
  if (session.attempt || session.busy || !configuration?.defaultContext) return;
  for (const key of ['discipline', 'knownFacts', 'goal', 'familiarity']) $(key === 'knownFacts' ? 'facts' : key).value = configuration.defaultContext[key];
  updateContextValidity();
  autoResize($('facts'), 280);
  autoResize($('goal'), 180);
  if (session.state === 'ERROR' && !session.attempt) session.recover();
});
for (const chip of document.querySelectorAll('.starter-chip')) {
  chip.addEventListener('click', () => {
    if (!session.canSend) return;
    const starter = chip.dataset.starter || '';
    const current = $('answer-text').value.trim();
    $('answer-text').value = chip.id === 'starter-full' || !current ? starter : `${current} ${starter}`;
    autoResize($('answer-text'));
    $('send-button').disabled = !session.canSend || !$('answer-text').value.trim();
    $('answer-text').focus();
  });
}
$('answer-text').addEventListener('input', () => {
  autoResize($('answer-text'));
  $('send-button').disabled = !session.canSend || (!session.attempt && !configuration?.configured.coaching) || !$('answer-text').value.trim();
});
$('answer-text').addEventListener('keydown', event => {
  if (event.isComposing) return;
  if (event.key === 'Enter' && (!event.shiftKey || event.ctrlKey || event.metaKey) && session.canSend && $('answer-text').value.trim()) {
    event.preventDefault();
    $('answer-form').requestSubmit();
  }
});
$('answer-form').addEventListener('submit', async event => {
  event.preventDefault();
  const answer = $('answer-text').value;
  if (!answer.trim() || !session.canSend) return;
  if (!session.snapshot) {
    if (!configuration?.configured.coaching || !validateContext()) return;
    $('answer-text').value = '';
    autoResize($('answer-text'));
    await session.startWithAnswer(readContext(), answer);
    if (!session.snapshot && !$('answer-text').value) {
      $('answer-text').value = answer;
      autoResize($('answer-text'));
      render(session);
    }
    return;
  }
  const before = session.answers;
  $('answer-text').value = '';
  autoResize($('answer-text'));
  await session.submitAnswer(answer);
  if (session.answers === before && !$('answer-text').value) {
    $('answer-text').value = answer;
    autoResize($('answer-text'));
    render(session);
  }
});
$('record-button').addEventListener('click', () => session.startRecording());
$('done-button').addEventListener('click', () => session.finishRecording());
$('play-button').addEventListener('click', () => player.resume());
$('finish-button').addEventListener('click', () => session.finish());
$('continue-button').addEventListener('click', () => session.recover());
$('recover-button').addEventListener('click', () => session.recover());
$('retry-voice-button').addEventListener('click', () => session.retryVoice());
$('mute-voice-button').addEventListener('click', () => session.setVoiceEnabled(false));
$('dismiss-voice-button').addEventListener('click', () => session.dismissVoiceError());
$('stop-button').addEventListener('click', () => session.stop());
$('reset-button').addEventListener('click', () => { session.reset(); $('answer-text').value = ''; autoResize($('answer-text')); });
$('retry-button').addEventListener('click', () => { session.retry(); $('practice').scrollIntoView({ block: 'start', behavior: 'smooth' }); });
$('hear-example').addEventListener('click', () => session.hearExample());
$('voice-enabled').addEventListener('change', event => session.setVoiceEnabled(event.target.checked));
$('how-button').addEventListener('click', () => $('how-dialog').showModal());
for (const id of ['setup-button', 'notice-setup']) $(id).addEventListener('click', () => $('setup-dialog').showModal());
for (const button of document.querySelectorAll('.close-dialog')) button.addEventListener('click', () => button.closest('dialog').close());
$('refresh-config').addEventListener('click', refreshConfiguration);
const clock = setInterval(() => {
  const seconds = session.state === 'LISTENING' && session.recordReady ? Math.min(60, Math.floor((Date.now() - session.recordStartedAt) / 1000)) : 0;
  $('recording-time').textContent = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}, 1000);
window.addEventListener('pagehide', () => { session.reset(); clearInterval(clock); });
session.subscribe(render);
refreshConfiguration();