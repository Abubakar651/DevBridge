// Same-origin HTTP transport. Credentials and coaching logic stay in Python.
export async function request(path, { data, audio, signal, method, keepalive = false } = {}) {
  const response = await fetch(`/api/${path}`, {
    method: method || (data !== undefined || audio ? 'POST' : 'GET'), signal, keepalive,
    headers: audio ? { 'Content-Type': audio.type || 'audio/webm' } : data !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: audio || (data !== undefined ? JSON.stringify(data) : undefined),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const error = new Error(body.error?.message || 'This step could not be completed. Please retry.');
    error.code = body.error?.code || 'REQUEST_FAILED'; throw error;
  }
  if (response.status === 204) return null;
  return path === 'speak' ? response.blob() : response.json();
}
const action = (id, name, requestId, signal, extra = {}) => request(`practice/${id}/${name}`, { data: { requestId, ...extra }, signal });
export const api = {
  config: () => request('config'),
  create: (context, requestId, signal) => request('practice', { data: { context, requestId }, signal }),
  answer: (id, text, requestId, signal) => action(id, 'answer', requestId, signal, { text }),
  advance: (id, requestId, signal) => action(id, 'advance', requestId, signal),
  finish: (id, requestId, signal) => action(id, 'finish', requestId, signal),
  retry: (id, requestId, signal) => action(id, 'retry', requestId, signal),
  stop: id => request(`practice/${id}/stop`, { method: 'POST', keepalive: true }),
  reset: id => request(`practice/${id}`, { method: 'DELETE', keepalive: true }),
  transcribe: (audio, signal) => request('transcribe', { audio, signal }),
  speak: (text, signal) => request('speak', { data: { text }, signal }),
  segments: async (text, signal) => (await request('speech/segments', { data: { text }, signal })).segments,
};
