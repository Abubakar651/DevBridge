export const cancelled = () => new DOMException('Cancelled', 'AbortError');

const AUDIO_MIME_PRESETS = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/ogg',
  'audio/mp4;codecs=mp4a.40.2',
  'audio/mp4',
  'audio/mpeg',
  'audio/wav',
];

export class Recorder {
  constructor({ mediaDevices = globalThis.navigator?.mediaDevices, RecorderClass = globalThis.MediaRecorder } = {}) {
    this.mediaDevices = mediaDevices; this.RecorderClass = RecorderClass; this.generation = 0;
  }
  get supported() { return Boolean(this.mediaDevices?.getUserMedia && this.RecorderClass); }
  _pickMime() {
    if (typeof this.RecorderClass?.isTypeSupported !== 'function') return undefined;
    return AUDIO_MIME_PRESETS.find(type => this.RecorderClass.isTypeSupported(type));
  }
  _createRecorder(stream, mime) {
    if (!mime) return new this.RecorderClass(stream);
    try {
      return new this.RecorderClass(stream, { mimeType: mime });
    } catch {
      return new this.RecorderClass(stream);
    }
  }
  _cleanupRecorder(recorder) {
    if (recorder) {
      recorder.onstop = null;
      recorder.ondataavailable = null;
      recorder.onerror = null;
      if (this.recorder === recorder) this.recorder = null;
    } else {
      this.recorder = null;
    }
    clearTimeout(this.timer);
    this.timer = null;
    this.parts = [];
    this.size = 0;
    this.limitReached = false;
    this.mime = '';
    this.release();
  }
  async start(onLimit, onError = () => {}) {
    if (!this.supported) throw new Error('Recording is unavailable in this browser. Type your answer instead.');
    this.cancel();
    const generation = this.generation;
    const stream = await this.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    if (generation !== this.generation) { stream.getTracks().forEach(track => track.stop()); throw cancelled(); }
    this.stream = stream;
    const mime = this._pickMime();
    try {
      const recorder = this._createRecorder(stream, mime);
      this.recorder = recorder;
      this.mime = recorder.mimeType || mime || '';
      this.parts = []; this.size = 0; this.limitReached = false;
      recorder.ondataavailable = event => {
        if (generation !== this.generation || !event.data?.size) return;
        this.parts.push(event.data); this.size += event.data.size;
        if (this.size > 5 * 1024 * 1024 && !this.limitReached) { this.limitReached = true; onLimit(); }
      };
      recorder.onerror = () => {
        if (generation !== this.generation) return;
        this.cancel(); onError(new Error('The microphone recording stopped unexpectedly. Please try again or type your answer.'));
      };
      recorder.start(250);
      this.timer = setTimeout(() => { if (generation === this.generation) onLimit(); }, 60_000);
    } catch (error) { this.cancel(); throw error; }
  }
  finish(signal) {
    if (!this.recorder || this.recorder.state === 'inactive') return Promise.reject(new Error('There is no active recording. Record your answer again.'));
    if (signal?.aborted) { this.cancel(); return Promise.reject(cancelled()); }
    clearTimeout(this.timer);
    this.timer = null;
    return new Promise((resolve, reject) => {
      const recorder = this.recorder;
      const fallbackMime = this.mime;
      let settled = false;
      const settle = (fn, value) => {
        if (settled) return;
        settled = true;
        signal?.removeEventListener('abort', abort);
        if (this.rejectFinish === abort) this.rejectFinish = null;
        this._cleanupRecorder(recorder);
        fn(value);
      };
      const abort = () => {
        recorder.onstop = null; recorder.ondataavailable = null; recorder.onerror = null;
        try { if (recorder.state !== 'inactive') recorder.stop(); } catch {}
        settle(reject, cancelled());
      };
      this.rejectFinish = abort;
      recorder.onstop = () => {
        const type = recorder.mimeType || fallbackMime || this.parts[0]?.type || 'audio/webm';
        const blob = new Blob(this.parts, { type });
        if (blob.size > 5 * 1024 * 1024) settle(reject, new Error('The recording exceeded 5 MB. Please record a shorter answer.'));
        else settle(resolve, blob);
      };
      recorder.onerror = () => settle(reject, new Error('The recording could not be completed. Please try again.'));
      signal?.addEventListener('abort', abort, { once: true });
      try {
        if (recorder.state === 'inactive') settle(reject, new Error('There is no active recording. Record your answer again.'));
        else recorder.stop();
      } catch {
        settle(reject, new Error('The recording could not be completed. Please try again.'));
      }
    });
  }
  release() { this.stream?.getTracks().forEach(track => track.stop()); this.stream = null; }
  cancel() {
    this.generation++;
    const reject = this.rejectFinish; this.rejectFinish = null;
    if (reject) {
      reject();
      return;
    }
    const recorder = this.recorder;
    if (recorder) {
      recorder.onstop = null; recorder.ondataavailable = null; recorder.onerror = null;
      try { if (recorder.state !== 'inactive') recorder.stop(); } catch {}
    }
    this._cleanupRecorder(recorder);
  }
}

export class SpeechPlayer {
  constructor(speak, { segmentText, createAudio = url => new Audio(url), createUrl = blob => URL.createObjectURL(blob), revokeUrl = url => URL.revokeObjectURL(url), guardMs = 200 } = {}) {
    this.speak = speak; this.createAudio = createAudio; this.createUrl = createUrl; this.revokeUrl = revokeUrl; this.guardMs = guardMs;
    this.segmentText = segmentText;
  }
  async play(text, { signal, onState, onBlocked } = {}) {
    if (signal?.aborted) throw cancelled();
    this.stop();
    onState?.('SYNTHESIZING');
    const segments = await this.segmentText(text, signal);
    if (signal?.aborted) throw cancelled();
    if (!segments.length) return;
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
            audio.onended = null; audio.onerror = null;
            try { audio.pause?.(); } catch {}
            this.current = null; onBlocked?.(false);
            error ? reject(error) : resolve();
          };
          const abort = () => finish(cancelled());
          const attempt = () => {
            if (signal?.aborted) return finish(cancelled());
            onState?.('SPEAKING');
            return Promise.resolve().then(() => audio.play()).then(() => onBlocked?.(false)).catch(error => {
              if (error?.name === 'NotAllowedError') onBlocked?.(true);
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
