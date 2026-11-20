// Browser I/O coordinator only. The Python server owns attempts, history and coaching.
export class PracticeSession {
  constructor({ api, recorder, player }) {
    this.api = api; this.recorder = recorder; this.player = player;
    this.listeners = new Set(); this.generation = 0; this.voiceEnabled = true;
    this.snapshot = null; this.state = 'IDLE'; this.pending = null; this.error = null; this.voiceError = null;
    this.blocked = false; this.queuedAnswer = null;
  }
  subscribe(listener) { this.listeners.add(listener); listener(this); return () => this.listeners.delete(listener); }
  emit() { for (const listener of this.listeners) listener(this); }
  get attempts() { return this.snapshot?.attempts || []; }
  get attempt() { return this.attempts.at(-1); }
  get context() { return this.snapshot?.context; }
  get serverStage() { return this.snapshot?.pendingStage; }
  get answers() { return this.attempt?.messages.filter(item => item.role === 'user').length || 0; }
  get canAnswer() { return this.state === 'IDLE' && !this.pending && !this.serverStage && !this.feedback && this.attempt?.messages.at(-1)?.role === 'assistant'; }
  get canType() { return !this.feedback && (!this.attempt || (!['THINKING', 'TRANSCRIBING', 'LISTENING'].includes(this.state) && this.serverStage !== 'coach')); }
  get canSend() {
    if (['THINKING', 'TRANSCRIBING', 'LISTENING'].includes(this.state) || this.feedback) return false;
    if (!this.attempt) return true;
    return !this.serverStage && this.attempt.messages.at(-1)?.role === 'assistant' && this.answers < (this.snapshot?.maxAnswers || 3);
  }
  get busy() { return !['IDLE', 'ERROR'].includes(this.state); }
  get feedback() { return this.attempt?.feedback; }
  apply(snapshot) { this.snapshot = snapshot; this.emit(); }
  setState(state) { this.state = state; this.emit(); }
  async start(context) {
    if (this.snapshot || this.busy) return;
    this.voiceError = null; this.queuedAnswer = null;
    this.pending = { type: 'create', context, id: crypto.randomUUID() };
    return this.runPending();
  }
  async startWithAnswer(context, text) {
    const trimmed = text.trim();
    if (this.snapshot || this.busy || !trimmed) return;
    this.voiceError = null; this.queuedAnswer = trimmed;
    this.pending = { type: 'create', context, id: crypto.randomUUID() };
    return this.runPending();
  }
  async submitAnswer(text) {
    const trimmed = text.trim();
    if (!this.canSend || !trimmed) return;
    if (this.pending?.type === 'speak' || ['SYNTHESIZING', 'SPEAKING'].includes(this.state)) {
      this.generation++; this.controller?.abort(); this.player.stop();
      this.blocked = false; this.state = 'IDLE'; this.pending = null;
    }
    this.voiceError = null;
    this.pending = { type: 'answer', text: trimmed, id: crypto.randomUUID() };
    return this.runPending();
  }
  async finish() {
    if (this.busy || !this.answers || this.feedback) return;
    this.voiceError = null;
    this.pending = { type: 'finish', id: crypto.randomUUID() };
    return this.runPending();
  }
  async retry() {
    if (this.busy || !this.feedback) return;
    this.voiceError = null;
    this.pending = { type: 'retry', id: crypto.randomUUID() };
    return this.runPending();
  }
  async retryVoice() {
    if (this.busy || !this.voiceError) return;
    const { text, speaker } = this.voiceError;
    this.voiceError = null;
    this.pending = { type: 'speak', text, speaker };
    return this.runPending();
  }
  dismissVoiceError() {
    if (!this.voiceError) return;
    this.voiceError = null; this.emit();
  }
  async runPending() {
    if (!this.pending || this.busy) return;
    const generation = ++this.generation;
    this.controller?.abort(); this.controller = new AbortController();
    const signal = this.controller.signal;
    const current = () => generation === this.generation && !signal.aborted;
    this.error = null;
    try {
      await this.stopping;
      while (this.pending && current()) {
        const stage = this.pending;
        if (stage.type === 'transcribe') {
          this.setState('TRANSCRIBING');
          const result = await this.api.transcribe(stage.audio, signal);
          if (!current()) return;
          if (!result.text?.trim()) { const error = new Error('No speech was transcribed. Record again or type your answer.'); error.code = 'EMPTY_TRANSCRIPT'; throw error; }
          this.pending = { type: 'answer', text: result.text.trim(), id: crypto.randomUUID() };
        } else if (stage.type === 'speak') {
          this.voiceError = null;
          if (this.voiceEnabled) {
            try {
              await this.player.play(stage.text, {
                signal,
                onState: state => { if (current()) this.setState(state); },
                onBlocked: blocked => { if (current()) { this.blocked = blocked; this.emit(); } },
              });
            } catch (error) {
              if (!current() || error.name === 'AbortError') return;
              this.voiceError = {
                message: error.message || 'Voice playback is unavailable right now. You can continue by typing or recording.',
                code: error.code || 'VOICE_FAILED',
                text: stage.text,
                speaker: stage.speaker || 'Coach',
              };
            }
          }
          if (!current()) return;
          this.pending = null;
        } else {
          this.setState('THINKING');
          let snapshot;
          const sessionId = this.snapshot?.sessionId;
          if (stage.type === 'create') snapshot = await this.api.create(stage.context, stage.id, signal);
          else if (stage.type === 'answer') snapshot = await this.api.answer(sessionId, stage.text, stage.id, signal);
          else if (stage.type === 'finish') snapshot = await this.api.finish(sessionId, stage.id, signal);
          else if (stage.type === 'retry') snapshot = await this.api.retry(sessionId, stage.id, signal);
          else snapshot = await this.api.advance(sessionId, stage.id, signal);
          if (!current()) return;
          this.apply(snapshot);
          if (stage.type === 'advance' && this.queuedAnswer && !snapshot.pendingStage && !snapshot.attempts.at(-1)?.feedback) {
            const queued = this.queuedAnswer;
            this.queuedAnswer = null;
            this.pending = { type: 'answer', text: queued, id: crypto.randomUUID() };
          } else {
            this.pending = stage.type === 'advance'
              ? (snapshot.playback ? { type: 'speak', ...snapshot.playback } : null)
              : { type: 'advance', id: crypto.randomUUID() };
          }
        }
      }
      if (current()) this.setState('IDLE');
    } catch (error) {
      if (!current() || error.name === 'AbortError') return;
      this.queuedAnswer = null;
      if (['EMPTY_TRANSCRIPT', 'EMPTY_RECORDING', 'ANSWER_TOO_LONG', 'INVALID_INPUT'].includes(error.code)) this.pending = null;
      this.error = { message: error.message || 'This step failed. Please retry.', code: error.code };
      this.setState('ERROR');
    }
  }
  async recover() {
    if (this.busy) return;
    this.error = null; this.state = 'IDLE';
    if (this.pending) return this.runPending();
    this.emit();
  }
  async startRecording() {
    if (!this.canAnswer) return;
    this.error = null; this.voiceError = null; this.recordReady = false;
    const generation = ++this.generation;
    this.setState('LISTENING');
    try {
      await this.recorder.start(() => { if (generation === this.generation) this.finishRecording(); }, error => {
        if (generation !== this.generation) return;
        this.recordReady = false; this.error = { message: error.message }; this.setState('ERROR');
      });
      if (generation !== this.generation) return;
      this.recordReady = true; this.recordStartedAt = Date.now(); this.emit();
    } catch (error) {
      if (generation !== this.generation || error.name === 'AbortError') return;
      this.error = { message: error.name === 'NotAllowedError' ? 'Microphone access was denied. Allow it in your browser, or type your answer instead.' : error.message };
      this.setState('ERROR');
    }
  }
  async finishRecording() {
    if (this.state !== 'LISTENING' || !this.recordReady) return;
    this.recordReady = false;
    const generation = this.generation;
    this.controller = new AbortController(); this.setState('TRANSCRIBING');
    try {
      const audio = await this.recorder.finish(this.controller.signal);
      if (generation !== this.generation) return;
      this.pending = { type: 'transcribe', audio }; this.state = 'IDLE';
      return this.runPending();
    } catch (error) {
      if (generation !== this.generation || error.name === 'AbortError') return;
      this.error = { message: error.message }; this.setState('ERROR');
    }
  }
  async hearExample() {
    if (this.busy || !this.feedback) return;
    this.voiceError = null;
    this.pending = { type: 'speak', text: this.feedback.improvedMessage, speaker: 'Coach' };
    return this.runPending();
  }
  async setVoiceEnabled(enabled) {
    this.voiceEnabled = enabled;
    if (!enabled) this.voiceError = null;
    if (!enabled && this.pending?.type === 'speak') { this.stop(); return this.recover(); }
    this.emit();
  }
  stop() {
    const stoppedSpeech = this.pending?.type === 'speak';
    this.generation++; this.controller?.abort(); this.player.stop(); this.recorder.cancel();
    const id = this.snapshot?.sessionId;
    this.stopping = id ? this.api.stop(id).catch(() => {}) : Promise.resolve();
    if (stoppedSpeech) this.pending = null;
    this.queuedAnswer = null; this.voiceError = null;
    this.recordReady = false; this.blocked = false; this.error = null; this.state = 'IDLE'; this.emit();
  }
  reset() {
    const id = this.snapshot?.sessionId;
    this.generation++; this.controller?.abort(); this.player.stop(); this.recorder.cancel();
    this.stopping = id ? this.api.reset(id).catch(() => {}) : Promise.resolve();
    this.queuedAnswer = null; this.voiceError = null;
    this.recordReady = false; this.blocked = false; this.error = null; this.state = 'IDLE';
    this.snapshot = null; this.pending = null; this.emit();
  }
}