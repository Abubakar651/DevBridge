export const cancelled = () => new DOMException('Cancelled', 'AbortError');

export class Recorder {
  constructor({ mediaDevices = globalThis.navigator?.mediaDevices, RecorderClass = globalThis.MediaRecorder } = {}) {
    this.mediaDevices = mediaDevices; this.RecorderClass = RecorderClass; this.generation = 0;
  }
  get supported() { return Boolean(this.mediaDevices?.getUserMedia && this.RecorderClass); }
  async start(onLimit, onError = () => {}) {
    if (!this.supported) throw new Error('Recording is unavailable in this browser. Type your answer instead.');
    this.cancel();
    const generation = this.generation;
    const stream = await this.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    if (generation !== this.generation) { stream.getTracks().forEach(track => track.stop()); throw cancelled(); }
    this.stream = stream;
    const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'].find(type => this.RecorderClass.isTypeSupported(type));
    try {
      this.recorder = new this.RecorderClass(stream, mime ? { mimeType: mime } : undefined);
      this.parts = []; this.size = 0;
      this.recorder.ondataavailable = event => {
        if (generation !== this.generation || !event.data.size) return;
        this.parts.push(event.data); this.size += event.data.size;
        if (this.size > 5 * 1024 * 1024 && !this.limitReached) { this.limitReached = true; onLimit(); }
      };
      this.recorder.onerror = () => {
        if (generation !== this.generation) return;
        this.cancel(); onError(new Error('The microphone recording stopped unexpectedly. Please try again or type your answer.'));
      };
      this.recorder.start(250);
      this.timer = setTimeout(() => { if (generation === this.generation) onLimit(); }, 60_000);
    } catch (error) { this.cancel(); throw error; }
  }
  finish(signal) {
    if (!this.recorder || this.recorder.state !== 'recording') return Promise.reject(new Error('There is no active recording. Record your answer again.'));
    clearTimeout(this.timer);
    return new Promise((resolve, reject) => {
      const recorder = this.recorder;
      const cleanup = () => { signal?.removeEventListener('abort', abort); this.rejectFinish = null; this.release(); };
      const abort = () => { cleanup(); reject(cancelled()); };
      this.rejectFinish = abort;
      recorder.onstop = () => {
        const blob = new Blob(this.parts, { type: recorder.mimeType }); cleanup();
        if (blob.size > 5 * 1024 * 1024) reject(new Error('The recording exceeded 5 MB. Please record a shorter answer.'));
        else resolve(blob);
      };
      recorder.onerror = () => { cleanup(); reject(new Error('The recording could not be completed. Please try again.')); };
      signal?.addEventListener('abort', abort, { once: true });
      recorder.stop();
    });
  }
  release() { this.stream?.getTracks().forEach(track => track.stop()); this.stream = null; }
  cancel() {
    this.generation++; clearTimeout(this.timer);
    const reject = this.rejectFinish; this.rejectFinish = null;
    if (this.recorder) {
      this.recorder.onstop = null; this.recorder.ondataavailable = null; this.recorder.onerror = null;
      if (this.recorder.state === 'recording') this.recorder.stop();
    }
    this.release(); this.recorder = null; this.parts = []; this.size = 0; this.limitReached = false;
    reject?.();
  }
}

export class SpeechPlayer {
  constructor(speak, { segmentText, createAudio = url => new Audio(url), createUrl = blob => URL.createObjectURL(blob), revokeUrl = url => URL.revokeObjectURL(url), guardMs = 200 } = {}) {
    this.speak = speak; this.createAudio = createAudio; this.createUrl = createUrl; this.revokeUrl = revokeUrl; this.guardMs = guardMs;
    this.segmentText = segmentText;
  }
  async play(text, { signal, onState, onBlocked } = {}) {
    onState?.('SYNTHESIZING');
    const segments = await this.segmentText(text, signal);
    for (const segment of segments) {
      if (signal?.aborted) throw cancelled();
      onState?.('SYNTHESIZING');
      const blob = await this.speak(segment, signal);
      if (signal?.aborted) throw cancelled();
      const url = this.createUrl(blob);
      try {
        await new Promise((resolve, reject) => {
          const audio = this.createAudio(url);
          let settled = false;
          const finish = error => {
            if (settled) return; settled = true;
            clearTimeout(watchdog); signal?.removeEventListener('abort', abort);
            audio.onended = null; audio.onerror = null; audio.pause();
            this.current = null; onBlocked?.(false);
            error ? reject(error) : resolve();
          };
          const abort = () => finish(cancelled());
          const attempt = () => {
            if (signal?.aborted) return finish(cancelled());
            onState?.('SPEAKING');
            return Promise.resolve(audio.play()).then(() => onBlocked?.(false)).catch(error => {
              if (error.name === 'NotAllowedError') onBlocked?.(true);
              else finish(new Error('Audio playback failed. Retry playback or switch spoken replies off.'));
            });
          };
          const watchdog = setTimeout(() => finish(new Error('Playback took too long. Retry it or continue in text.')), 180_000);
          this.current = { audio, abort, attempt };
          audio.onended = () => finish();
          audio.onerror = () => finish(new Error('Audio could not be played. Retry or continue in text.'));
          signal?.addEventListener('abort', abort, { once: true });
          attempt();
        });
      } finally { this.revokeUrl(url); }
    }
    if (signal?.aborted) throw cancelled();
    await new Promise((resolve, reject) => {
      const abort = () => { clearTimeout(timer); signal?.removeEventListener('abort', abort); reject(cancelled()); };
      const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, this.guardMs);
      signal?.addEventListener('abort', abort, { once: true });
    });
  }
  resume() { return this.current?.attempt(); }
  stop() { this.current?.abort(); }
}
