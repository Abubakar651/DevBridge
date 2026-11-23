import { api } from './api.js';
import { Recorder, SpeechPlayer } from './audio.js';
import { PracticeSession } from './session.js';

const $ = id => document.getElementById(id);
const THEME_KEY = 'devbridge-theme';
const recorder = new Recorder();
const player = new SpeechPlayer(api.speak, { segmentText: api.segments });
const session = new PracticeSession({ api, recorder, player });
const supportsFieldSizing = typeof CSS !== 'undefined' && CSS.supports?.('field-sizing', 'content');
let configuration = null;
let messageSignature = '';
let feedbackSignature = '';
let errorSignature = '';
let configError = '';
let isOffline = typeof navigator !== 'undefined' && navigator.onLine === false;
let contextInitialized = false;
let briefMode = 'edit';
let sceneOpen = false;
let coachOpen = false;

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

const themeButtons = [
  ['auto', $('theme-auto')],
  ['light', $('theme-light')],
  ['dark', $('theme-dark')],
];
function applyTheme(theme, persist = true) {
  const mode = theme === 'light' || theme === 'dark' ? theme : 'auto';
  document.documentElement.dataset.theme = mode;
  for (const [value, button] of themeButtons) {
    if (!button) continue;
    const active = value === mode;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
  }
  if (persist) {
    try { localStorage.setItem(THEME_KEY, mode); } catch { /* ignore storage errors */ }
  }
}

function syncOfflineUI() {
  isOffline = typeof navigator !== 'undefined' && navigator.onLine === false;
  if ($('offline-notice')) $('offline-notice').hidden = !isOffline;
  if (isOffline) {
    if ($('setup-badge-label')) $('setup-badge-label').textContent = 'Offline';
    if ($('setup-dot')) {
      $('setup-dot').classList.add('is-offline');
      $('setup-dot').classList.remove('is-warn');
    }
  }
}

function renderSceneBrief() {
  const chips = element('div', 'brief-chips');
  const personaLabel = selectedPersona()?.label;
  const roleLabel = $('discipline').selectedOptions?.[0]?.textContent || $('discipline').value;
  const audienceLabel = $('familiarity').selectedOptions?.[0]?.textContent || $('familiarity').value;
  const difficultyTag = selectedDifficulty()?.tag;
  if (personaLabel) chips.append(element('span', 'brief-chip', personaLabel));
  if (roleLabel) chips.append(element('span', 'brief-chip', roleLabel));
  if (audienceLabel) chips.append(element('span', 'brief-chip', audienceLabel));
  if (difficultyTag) chips.append(element('span', 'brief-chip', difficultyTag));

  const factsBlock = element('div', 'brief-block');
  factsBlock.append(element('strong', '', 'Key facts'));
  paragraph(factsBlock, '', $('facts').value.trim() || 'No facts entered yet.');

  const goalBlock = element('div', 'brief-block');
  goalBlock.append(element('strong', '', 'Your goal'));
  paragraph(goalBlock, '', $('goal').value.trim() || 'No goal entered yet.');

  $('scene-brief').replaceChildren(chips, factsBlock, goalBlock);
}

function setBriefMode(mode) {
  briefMode = mode === 'brief' ? 'brief' : 'edit';
  if (briefMode === 'brief') renderSceneBrief();
  $('scene-brief').hidden = briefMode !== 'brief';
  $('context-form').hidden = briefMode === 'brief';
  $('brief-mode-brief').classList.toggle('is-active', briefMode === 'brief');
  $('brief-mode-brief').setAttribute('aria-pressed', briefMode === 'brief' ? 'true' : 'false');
  $('brief-mode-edit').classList.toggle('is-active', briefMode === 'edit');
  $('brief-mode-edit').setAttribute('aria-pressed', briefMode === 'edit' ? 'true' : 'false');
  if (briefMode === 'edit') {
    autoResize($('facts'), 280);
    autoResize($('goal'), 180);
  }
}

function setSceneOpen(open) {
  sceneOpen = Boolean(open);
  $('context-panel').hidden = !sceneOpen;
  $('workspace').dataset.sceneOpen = sceneOpen ? 'true' : 'false';
  $('scene-toggle').classList.toggle('is-active', sceneOpen);
  $('scene-toggle').setAttribute('aria-expanded', sceneOpen ? 'true' : 'false');
  if ($('header-scenario-pill')) {
    $('header-scenario-pill').classList.toggle('is-active', sceneOpen);
    $('header-scenario-pill').setAttribute('aria-expanded', sceneOpen ? 'true' : 'false');
  }
  if (sceneOpen && briefMode === 'edit') {
    autoResize($('facts'), 280);
    autoResize($('goal'), 180);
  }
}

function setCoachOpen(open) {
  coachOpen = Boolean(open);
  $('coach-panel').hidden = !coachOpen;
  $('workspace').dataset.coachOpen = coachOpen ? 'true' : 'false';
  $('coach-toggle').classList.toggle('is-active', coachOpen);
  $('coach-toggle').setAttribute('aria-expanded', coachOpen ? 'true' : 'false');
}

function selectedScenario() {
  const list = configuration?.scenarios || (configuration?.scenario ? [configuration.scenario] : []);
  const currentId = $('scenario')?.value || configuration?.scenario?.id;
  return list.find(item => item.id === currentId) || configuration?.scenario || null;
}

function selectedPersona() {
  const scenario = selectedScenario();
  const list = configuration?.personas || [];
  const currentId = $('persona')?.value || scenario?.personaId;
  const found = list.find(item => item.id === currentId);
  if (found) return found;
  const selectedLabel = $('persona')?.selectedOptions?.[0]?.textContent;
  return {
    id: currentId || scenario?.personaId || 'project-manager',
    label: selectedLabel || scenario?.stakeholder || 'Project manager',
    tag: scenario?.stakeholderTag || selectedLabel || scenario?.stakeholder || 'PM',
    avatar: scenario?.avatar || 'PM',
  };
}

function selectedDifficulty() {
  const list = configuration?.difficulties || [];
  const currentId = $('difficulty')?.value || 'standard';
  const found = list.find(item => item.id === currentId);
  if (found) return found;
  const selectedLabel = $('difficulty')?.selectedOptions?.[0]?.textContent;
  return {
    id: currentId,
    label: selectedLabel || 'Standard · realistic check-in',
    tag: currentId.charAt(0).toUpperCase() + currentId.slice(1),
  };
}

function isContextCustomized() {
  const scenario = selectedScenario();
  const defaults = scenario?.defaultContext;
  if (!scenario || !defaults) return false;
  return (
    ($('persona')?.value || scenario.personaId) !== scenario.personaId
    || ($('difficulty')?.value || defaults.difficulty || 'standard') !== (defaults.difficulty || 'standard')
    || ($('discipline')?.value || defaults.discipline) !== defaults.discipline
    || ($('familiarity')?.value || defaults.familiarity) !== defaults.familiarity
    || ($('facts')?.value.trim() ?? defaults.knownFacts) !== defaults.knownFacts
    || ($('goal')?.value.trim() ?? defaults.goal) !== defaults.goal
  );
}

function stakeholderProse(label) {
  const text = (label || 'project manager').trim();
  return /^[A-Z]{2,}\b/.test(text) ? text : text.charAt(0).toLowerCase() + text.slice(1);
}

function syncPersonaUI() {
  const scenario = selectedScenario();
  const persona = selectedPersona();
  if ($('header-scenario-pill') && scenario) {
    $('header-scenario-pill').textContent = `${scenario.title} · ${persona.tag || persona.label} · ${scenario.duration}`;
  }
  if ($('scenario-stakeholder')) $('scenario-stakeholder').textContent = persona.label;
  if ($('scenario-custom-badge')) {
    const customized = isContextCustomized();
    $('scenario-custom-badge').hidden = !customized;
    $('scenario-custom-badge').textContent = (scenario && persona.id !== scenario.personaId) ? 'Custom mix' : 'Customized';
  }
  if ($('scenario-description')) {
    $('scenario-description').textContent = (scenario && persona.id !== scenario.personaId)
      ? `Custom audience: practising ${scenario.title.toLowerCase()} with your ${stakeholderProse(persona.label)}.`
      : (scenario?.description || '');
  }
  if ($('composer-prompt-label')) $('composer-prompt-label').textContent = `Message your ${stakeholderProse(persona.label)}`;
  if ($('empty-subtitle')) {
    const text = scenario?.emptySubtitle && persona.id === scenario.personaId
      ? scenario.emptySubtitle
      : `Your ${stakeholderProse(persona.label)} will start the conversation.\nSpeak or type — pause, rethink, and try again anytime.`;
    const lines = text.split('\n');
    const nodes = [];
    lines.forEach((line, idx) => {
      if (idx > 0) nodes.push(document.createElement('br'));
      nodes.push(document.createTextNode(line));
    });
    $('empty-subtitle').replaceChildren(...nodes);
  }
  if (briefMode === 'brief') renderSceneBrief();
  render(session);
}

function applyScenario(scenarioId, resetFields = true) {
  const list = configuration?.scenarios || (configuration?.scenario ? [configuration.scenario] : []);
  const scenario = list.find(item => item.id === scenarioId) || configuration?.scenario;
  if (!scenario) return;
  if ($('scenario')) $('scenario').value = scenario.id;
  if ($('scenario-title')) $('scenario-title').textContent = scenario.title;
  if ($('scenario-description')) $('scenario-description').textContent = scenario.description;
  if ($('scenario-duration')) $('scenario-duration').textContent = scenario.duration;
  if ($('empty-headline') && scenario.emptyHeadline) $('empty-headline').textContent = scenario.emptyHeadline;
  if ($('easy-start-steps') && Array.isArray(scenario.steps)) {
    const stepNodes = scenario.steps.map(step => {
      const span = document.createElement('span');
      span.append(element('strong', '', step.label), ` ${step.text}`);
      return span;
    });
    $('easy-start-steps').replaceChildren(...stepNodes);
  }
  if (scenario.starters) {
    for (const [key, id] of [['full', 'starter-full'], ['ready', 'starter-ready'], ['tradeoff', 'starter-tradeoff'], ['recommend', 'starter-recommend']]) {
      if ($(id) && scenario.starters[key]) $(id).dataset.starter = scenario.starters[key];
      if ($(id) && scenario.starterLabels?.[key]) $(id).textContent = scenario.starterLabels[key];
    }
  }
  if ($('answer-text') && scenario.placeholder) $('answer-text').placeholder = scenario.placeholder;

  if (resetFields && scenario.defaultContext) {
    if ($('persona')) $('persona').value = scenario.personaId || configuration?.personas?.[0]?.id || 'vp-ops';
    if ($('difficulty')) $('difficulty').value = scenario.defaultContext.difficulty || 'standard';
    for (const key of ['discipline', 'knownFacts', 'goal', 'familiarity']) {
      $(key === 'knownFacts' ? 'facts' : key).value = scenario.defaultContext[key];
    }
    for (const [, errorNode] of contextChecks) {
      errorNode.textContent = '';
      errorNode.hidden = true;
    }
    updateContextValidity(false);
    autoResize($('facts'), 280);
    autoResize($('goal'), 180);
    renderSceneBrief();
  }
  syncPersonaUI();
}

function renderMessages(state) {
  const messages = state.attempt?.messages || [];
  const signature = JSON.stringify([state.attempt?.number, messages]);
  if (signature === messageSignature) return;
  messageSignature = signature;
  $('messages').replaceChildren();
  const stakeholderLabel = (selectedPersona()?.label || 'Stakeholder').toUpperCase();
  for (const message of messages) {
    const item = element('li', `message ${message.role}`);
    item.append(element('div', 'message-label', message.role === 'user' ? 'YOU' : stakeholderLabel));
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
  setCoachOpen(true);
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

const DEFAULT_CHECKLIST_DIMENSIONS = [
  { id: 'Audience clarity', label: 'Plain language' },
  { id: 'Structure and relevance', label: 'A clear point' },
  { id: 'Assertiveness', label: 'Confident recommendations' },
  { id: 'Respect', label: 'Respectful wording' },
  { id: 'Accuracy and next steps', label: 'Facts & a next step' },
];

function renderComparison(state) {
  $('comparison').hidden = state.attempts.length < 2;
  if (state.attempts.length < 2) return;
  const previous = state.attempts.at(-2);
  const current = state.attempt;
  const body = element('div', 'comparison-body');
  const fallbackFocus = previous?.feedback?.retryFocus || 'Make your core message and recommendation clear.';
  paragraph(body, '', current?.feedback?.comparison || `Your focus: ${fallbackFocus}`);

  const dimensions = configuration?.checklistDimensions || DEFAULT_CHECKLIST_DIMENSIONS;
  const prevFlagged = new Set((previous?.feedback?.improvements || []).map(item => item.dimension));
  const currFlagged = new Set((current?.feedback?.improvements || []).map(item => item.dimension));
  const hasCurrentFeedback = Boolean(current?.feedback);
  const checklistGrid = element('div', 'checklist-comparison');
  checklistGrid.id = 'checklist-comparison';
  for (const dim of dimensions) {
    const card = element('div', 'checklist-item');
    const header = element('div', '');
    header.append(
      element('div', 'checklist-item-title', dim.id),
      element('div', 'checklist-item-subtitle', dim.label || ''),
    );
    let badgeText = 'Strong ✓';
    let badgeClass = 'checklist-badge is-strong';
    if (hasCurrentFeedback) {
      if (currFlagged.has(dim.id)) {
        badgeText = 'Focus next';
        badgeClass = 'checklist-badge is-focus';
      } else if (prevFlagged.has(dim.id)) {
        badgeText = 'Improved ✓';
        badgeClass = 'checklist-badge is-improved';
      }
    } else if (prevFlagged.has(dim.id)) {
      badgeText = 'Practising now';
      badgeClass = 'checklist-badge is-focus';
    }
    card.append(header, element('span', badgeClass, badgeText));
    checklistGrid.append(card);
  }
  body.append(checklistGrid);

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
  if (state.state === 'LISTENING') {
    if (!state.recordReady) return 'Waiting for microphone permission…';
    if (state.voiceActivity?.speaking) return 'Hearing you clearly — keep going.';
    if (state.voiceActivity?.speechDetected && state.autoStopSilence) return 'Pause detected — auto-finishing in a moment, or click Done speaking.';
    return state.autoStopSilence ? 'Listening. Speak naturally — pauses auto-finish, or click Done speaking.' : 'Listening. Click Done speaking when you finish.';
  }
  if (state.state === 'TRANSCRIBING') return 'Turning your answer into text…';
  if (state.state === 'THINKING') return state.serverStage === 'coach' ? 'Your coach is reflecting on the conversation…' : `Your ${stakeholderProse(selectedPersona()?.label)} is thinking…`;
  if (state.state === 'SYNTHESIZING') return 'Preparing the spoken reply…';
  if (state.state === 'SPEAKING') return state.blocked ? 'Your browser needs a tap to play audio.' : `${state.pending?.speaker || 'Your coach'} is speaking…`;
  if (state.state === 'ERROR') return state.answers ? 'Your accepted answers are still here.' : 'Nothing was submitted. Review the details and try again.';
  if (state.pending) return 'Paused. Continue when you’re ready.';
  if (state.feedback) return 'Your coaching notes are ready.';
  if (state.canAnswer) return state.voiceError ? 'Your turn (spoken audio paused — type or speak below).' : 'Your turn. Take your time.';
  return 'Ready when you are';
}

function render(state) {
  syncOfflineUI();
  document.body.dataset.state = state.state;
  $('practice').setAttribute('aria-busy', state.busy ? 'true' : 'false');
  const active = Boolean(state.attempt);
  const coaching = Boolean(state.feedback) || (state.serverStage === 'coach' && state.state === 'THINKING');
  const canCoachStart = Boolean(configuration?.configured.coaching) && !isOffline;
  const maxAnswers = configuration?.maxAnswers || 10;
  $('state-label').textContent = stateLabel(state);
  $('turn-count').textContent = `${state.answers} / ${maxAnswers} answers`;
  const turnSteps = $('turn-steps');
  if (turnSteps && turnSteps.children.length !== maxAnswers) {
    turnSteps.replaceChildren(...Array.from({ length: maxAnswers }, () => document.createElement('span')));
  }
  const stepSpans = turnSteps?.querySelectorAll('span') || [];
  stepSpans.forEach((span, index) => {
    span.classList.toggle('is-done', index < state.answers);
    span.classList.toggle('is-active', active && !state.feedback && index === state.answers && state.answers < maxAnswers);
  });
  const persona = selectedPersona();
  const stakeholder = persona?.label || 'Project manager';
  const avatar = persona?.avatar || 'PM';
  $('attempt-label').textContent = active ? `ATTEMPT ${state.attempt.number}` : 'FIRST ATTEMPT';
  $('partner-name').textContent = coaching ? 'Your communication coach' : `Your ${stakeholderProse(stakeholder)}`;
  $('partner-description').textContent = coaching ? 'Specific feedback, with your facts intact' : 'A simulated workplace conversation';
  $('partner-avatar').textContent = coaching ? 'VC' : avatar;
  if ($('composer-prompt-label')) $('composer-prompt-label').textContent = `Message your ${stakeholderProse(stakeholder)}`;
  $('mode-badge').textContent = coaching ? 'COACHING' : 'ROLE-PLAY';
  $('start-button').hidden = active;
  $('start-button').disabled = !canCoachStart;
  $('record-button').hidden = !active || Boolean(state.feedback) || state.state === 'LISTENING';
  $('record-button').disabled = !state.canAnswer || !configuration?.configured.groq || !recorder.supported || isOffline;
  $('done-button').hidden = state.state !== 'LISTENING';
  $('done-button').disabled = !state.recordReady;
  $('play-button').hidden = !state.blocked;
  $('continue-button').hidden = !state.pending || state.busy || state.state === 'ERROR';
  $('finish-button').hidden = !active || Boolean(state.feedback) || state.serverStage === 'coach';
  $('finish-button').disabled = state.busy || !state.answers || isOffline;
  $('stop-button').disabled = !state.busy;
  $('reset-button').disabled = !active;
  $('mic-status').textContent = state.state === 'LISTENING'
    ? (!state.recordReady
      ? 'Requesting mic…'
      : state.voiceActivity?.speaking
        ? 'Voice detected'
        : state.voiceActivity?.speechDetected && state.autoStopSilence
          ? 'Pause · auto-send'
          : (state.autoStopSilence ? 'Listening · auto-pause' : 'Recording · up to 60s'))
    : 'Mic off';
  $('mic-status').classList.toggle('is-speaking', state.state === 'LISTENING' && Boolean(state.voiceActivity?.speaking));
  if ($('auto-silence')) {
    $('auto-silence').checked = Boolean(state.autoStopSilence);
    $('auto-silence').disabled = !configuration?.configured.groq || !recorder.supported;
  }
  const speechConfigured = Boolean(configuration?.configured.speech);
  $('voice-enabled').disabled = !speechConfigured;
  $('voice-enabled').checked = configuration ? Boolean(state.voiceEnabled && speechConfigured) : state.voiceEnabled;
  $('voice-notice').hidden = !state.voiceError;
  $('voice-notice-message').textContent = state.voiceError?.message || '';
  $('retry-voice-button').disabled = state.busy;
  $('type-answer').hidden = Boolean(state.feedback);
  $('send-button').hidden = Boolean(state.feedback);
  $('coaching-dock-note').hidden = !state.feedback || state.blocked || Boolean(state.pending && !state.busy && state.state !== 'ERROR');
  $('answer-text').disabled = !state.canType || (!active && !canCoachStart);
  $('send-button').disabled = !state.canSend || (!active && !canCoachStart) || !$('answer-text').value.trim() || isOffline;
  $('answer-hint').textContent = isOffline
    ? 'You’re offline. Reconnect to continue live practice.'
    : !canCoachStart
      ? 'Connect Gemini or Groq in Practice setup to chat.'
      : !active
        ? 'Write an update and press Send to begin, or click Start practice.'
        : state.state === 'ERROR'
          ? (state.queuedAnswer ? 'Your draft is saved — click Retry above to submit it.' : 'This step needs another try — use the retry button in the banner above.')
          : state.canSend
            ? (state.state === 'SPEAKING' || state.state === 'SYNTHESIZING' ? 'Your words. Sending interrupts audio.' : 'Your words. No perfect script needed.')
            : (state.pending && !state.busy ? 'Practice paused — click Continue practice to resume.' : 'Wait until the current step finishes.');
  $('starter-bar').hidden = !active || Boolean(state.feedback);
  for (const chip of document.querySelectorAll('.starter-chip')) chip.disabled = !state.canSend;
  $('coach-toggle-badge').hidden = !state.feedback;
  $('retry-button').disabled = state.busy || isOffline;
  if ($('use-example-button')) $('use-example-button').disabled = state.busy || !state.feedback?.improvedMessage;
  $('hear-example').disabled = state.busy || !state.voiceEnabled || !configuration?.configured.speech;
  if (state.state === 'ERROR' && state.lastTranscribedText && !$('answer-text').value) {
    $('answer-text').value = state.lastTranscribedText;
    state.lastTranscribedText = '';
    autoResize($('answer-text'));
  }
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
      if ($('scenario') && Array.isArray(configuration.scenarios)) {
        const opts = configuration.scenarios.map(item => {
          const opt = document.createElement('option');
          opt.value = item.id;
          opt.textContent = item.title;
          return opt;
        });
        $('scenario').replaceChildren(...opts);
      }
      if ($('persona') && Array.isArray(configuration.personas)) {
        const personaOpts = configuration.personas.map(item => {
          const opt = document.createElement('option');
          opt.value = item.id;
          opt.textContent = item.label;
          return opt;
        });
        $('persona').replaceChildren(...personaOpts);
      }
      if ($('familiarity') && Array.isArray(configuration.familiarityOptions)) {
        const famOpts = configuration.familiarityOptions.map(item => {
          const opt = document.createElement('option');
          opt.value = item.value;
          opt.textContent = item.label;
          return opt;
        });
        $('familiarity').replaceChildren(...famOpts);
      }
      if ($('difficulty') && Array.isArray(configuration.difficulties)) {
        const diffOpts = configuration.difficulties.map(item => {
          const opt = document.createElement('option');
          opt.value = item.id;
          opt.textContent = item.label;
          return opt;
        });
        $('difficulty').replaceChildren(...diffOpts);
      }
      contextInitialized = true;
      applyScenario(configuration.defaultContext.scenarioId, true);
    }
    $('gemini-status').textContent = configuration.configured.gemini ? 'Key found' : 'Key missing';
    $('groq-status').textContent = configuration.configured.groq ? 'Key found' : configuration.configured.speech ? 'Output key found' : 'Key missing';
    $('test-notice').hidden = configuration.mode === 'live';
    if (!configuration.configured.speech) await session.setVoiceEnabled(false);
  } catch { configError = 'The local server is unavailable. Start it and check configuration again.'; }
  $('configuration-notice').hidden = !configError && Boolean(configuration?.configured.coaching && configuration?.configured.groq && configuration?.configured.speech);
  $('configuration-message').textContent = configError || (!configuration?.configured.coaching ? 'Connect Gemini or Groq to start your practice conversation. Your scenario is ready below.' : !configuration?.configured.groq ? 'Voice input is not configured yet. You can practise by typing.' : 'Spoken replies are not configured yet. Switch them off to continue practice.');
  const badgeLabel = $('setup-badge-label');
  const badgeDot = $('setup-dot');
  if (badgeLabel) {
    badgeLabel.textContent = configError
      ? 'Server offline'
      : !configuration?.configured.coaching
        ? 'Setup needed'
        : configuration.mode === 'live'
          ? 'Live practice'
          : 'Test mode';
  }
  if (badgeDot) {
    badgeDot.classList.toggle('is-offline', Boolean(configError));
    badgeDot.classList.toggle('is-warn', !configError && !configuration?.configured.coaching);
  }
  $('refresh-config').disabled = false;
  render(session);
}

$('context-form').noValidate = true;
$('context-form').addEventListener('submit', event => event.preventDefault());
const contextChecks = [
  [$('facts'), $('facts-error'), 20, 'Add at least 20 visible characters describing what is known.'],
  [$('goal'), $('goal-error'), 10, 'Add at least 10 visible characters describing what you want to communicate.'],
];
function updateContextValidity(showErrors = false) {
  let allValid = true;
  let firstInvalid = null;
  for (const [input, errorNode, minimum, message] of contextChecks) {
    const invalid = input.value.trim().length < minimum;
    input.setCustomValidity(invalid ? message : '');
    if (invalid) {
      allValid = false;
      if (!firstInvalid) firstInvalid = input;
    }
    const displayError = invalid && (showErrors || !errorNode.hidden);
    input.classList.toggle('is-invalid', displayError);
    if (displayError) {
      input.setAttribute('aria-invalid', 'true');
      errorNode.textContent = message;
      errorNode.hidden = false;
    } else {
      input.removeAttribute('aria-invalid');
      if (!invalid) {
        errorNode.textContent = '';
        errorNode.hidden = true;
      }
    }
  }
  return { allValid, firstInvalid };
}
function validateContext() {
  const { allValid, firstInvalid } = updateContextValidity(true);
  if (!allValid) {
    setSceneOpen(true);
    setBriefMode('edit');
    firstInvalid?.focus();
  }
  return allValid;
}
function readContext() {
  return {
    scenarioId: $('scenario')?.value || configuration.scenario.id,
    personaId: $('persona')?.value || selectedScenario()?.personaId,
    difficulty: $('difficulty')?.value || 'standard',
    discipline: $('discipline').value,
    knownFacts: $('facts').value.trim(),
    goal: $('goal').value.trim(),
    familiarity: $('familiarity').value,
  };
}
for (const [input] of contextChecks) {
  input.addEventListener('input', () => {
    updateContextValidity(false);
    autoResize(input, input.id === 'goal' ? 180 : 280);
    syncPersonaUI();
  });
}
for (const id of ['discipline', 'familiarity', 'difficulty']) {
  $(id)?.addEventListener('change', () => { syncPersonaUI(); });
}
if ($('scenario')) {
  $('scenario').addEventListener('change', event => {
    if (session.attempt || session.busy) return;
    applyScenario(event.target.value, true);
  });
}
if ($('persona')) {
  $('persona').addEventListener('change', () => {
    if (session.attempt || session.busy) return;
    syncPersonaUI();
  });
}

let savedTheme = 'auto';
try { savedTheme = localStorage.getItem(THEME_KEY) || 'auto'; } catch { savedTheme = 'auto'; }
applyTheme(savedTheme, false);
for (const [mode, button] of themeButtons) button?.addEventListener('click', () => applyTheme(mode));
$('brief-mode-brief').addEventListener('click', () => setBriefMode('brief'));
$('brief-mode-edit').addEventListener('click', () => setBriefMode('edit'));
$('scene-toggle').addEventListener('click', () => setSceneOpen(!sceneOpen));
$('header-scenario-pill')?.addEventListener('click', () => setSceneOpen(!sceneOpen));
$('empty-scene-button')?.addEventListener('click', () => { setSceneOpen(true); setBriefMode('edit'); $('scenario')?.focus(); });
$('coach-toggle').addEventListener('click', () => setCoachOpen(!coachOpen));
$('close-scene-button').addEventListener('click', () => { setSceneOpen(false); $('scene-toggle').focus(); });
$('close-coach-button').addEventListener('click', () => { setCoachOpen(false); $('coach-toggle').focus(); });

$('start-button').addEventListener('click', () => {
  if (!validateContext()) return;
  session.start(readContext());
});
$('reset-scene-button').addEventListener('click', () => {
  if (session.attempt || session.busy) return;
  const fallback = selectedScenario()?.defaultContext || configuration?.defaultContext;
  if (!fallback) return;
  applyScenario(fallback.scenarioId, true);
  if (session.state === 'ERROR' && !session.attempt) session.recover();
});
function setMobileStartersOpen(open) {
  const expanded = Boolean(open);
  if ($('starter-bar')) $('starter-bar').dataset.mobileOpen = expanded ? 'true' : 'false';
  if ($('starter-mobile-toggle')) $('starter-mobile-toggle').setAttribute('aria-expanded', expanded ? 'true' : 'false');
  if ($('starter-mobile-hint')) $('starter-mobile-hint').textContent = expanded ? 'Hide' : 'Show 4';
}
$('starter-mobile-toggle')?.addEventListener('click', () => {
  setMobileStartersOpen($('starter-bar')?.dataset.mobileOpen !== 'true');
});
for (const chip of document.querySelectorAll('.starter-chip')) {
  chip.addEventListener('click', () => {
    if (!session.canSend) return;
    const starter = chip.dataset.starter || '';
    const current = $('answer-text').value.trim();
    $('answer-text').value = chip.id === 'starter-full' || !current ? starter : `${current} ${starter}`;
    autoResize($('answer-text'));
    $('send-button').disabled = !session.canSend || !$('answer-text').value.trim();
    setMobileStartersOpen(false);
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
      session.queuedAnswer = null;
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
$('reset-button').addEventListener('click', () => { setCoachOpen(false); session.reset(); $('answer-text').value = ''; autoResize($('answer-text')); });
$('retry-button').addEventListener('click', () => { setCoachOpen(false); session.retry(); $('practice').scrollIntoView({ block: 'start', behavior: 'smooth' }); });
$('use-example-button')?.addEventListener('click', async () => {
  const draft = session.feedback?.improvedMessage?.trim() || '';
  if (!draft || session.busy) return;
  setCoachOpen(false);
  await session.retry();
  $('answer-text').value = draft;
  autoResize($('answer-text'));
  render(session);
  $('answer-text').focus();
});
$('hear-example').addEventListener('click', () => session.hearExample());
$('auto-silence')?.addEventListener('change', event => session.setAutoStopSilence(event.target.checked));
$('voice-enabled').addEventListener('change', event => {
  const enabled = Boolean(event.target.checked && configuration?.configured.speech);
  event.target.checked = enabled;
  session.setVoiceEnabled(enabled);
});
$('how-button').addEventListener('click', () => $('how-dialog').showModal());
for (const id of ['setup-button', 'notice-setup']) $(id).addEventListener('click', () => $('setup-dialog').showModal());
for (const button of document.querySelectorAll('.close-dialog')) button.addEventListener('click', () => button.closest('dialog').close());
$('refresh-config').addEventListener('click', refreshConfiguration);
const clock = setInterval(() => {
  const seconds = session.state === 'LISTENING' && session.recordReady ? Math.min(60, Math.floor((Date.now() - session.recordStartedAt) / 1000)) : 0;
  $('recording-time').textContent = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}, 1000);
window.addEventListener('pagehide', () => { session.reset(); clearInterval(clock); });
window.addEventListener('offline', () => { syncOfflineUI(); render(session); });
window.addEventListener('online', () => { syncOfflineUI(); refreshConfiguration(); });
$('offline-retry-button')?.addEventListener('click', () => { syncOfflineUI(); if (!isOffline) refreshConfiguration(); });
syncOfflineUI();
if (typeof navigator !== 'undefined' && 'serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === '127.0.0.1' || location.hostname === 'localhost')) {
  navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
}
session.subscribe(render);
refreshConfiguration();
