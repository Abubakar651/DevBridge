// Same-origin HTTP transport. Credentials and coaching logic stay in Python.
const apiError = (message, code, status) => {
  const error = new Error(message);
  error.code = code;
  if (status !== undefined) error.status = status;
  return error;
};

const sessionPath = (id, suffix = '') => {
  if (typeof id !== 'string' || !id.trim()) {
    throw apiError('The practice session is missing. Reset and start again.', 'INVALID_INPUT');
  }
  const encoded = encodeURIComponent(id);
  return suffix ? `practice/${encoded}/${suffix}` : `practice/${encoded}`;
};

export async function request(path, { data, audio, signal, method, keepalive = false } = {}) {
  const cleanPath = String(path).replace(/^\/+/, '');
  const contentType = audio ? (audio.type || '').trim() || 'audio/webm' : data !== undefined ? 'application/json' : null;
  let response;
  try {
    response = await fetch(`/api/${cleanPath}`, {
      method: method || (data !== undefined || audio ? 'POST' : 'GET'),
      signal,
      keepalive,
      headers: contentType ? { 'Content-Type': contentType } : {},
      body: audio || (data !== undefined ? JSON.stringify(data) : undefined),
    });
  } catch (error) {
    if (error?.name === 'AbortError' || signal?.aborted) throw error;
    throw apiError('Could not reach the local server. Check that it is running and retry.', 'NETWORK_ERROR');
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw apiError(body.error?.message || 'This step could not be completed. Please retry.', body.error?.code || 'REQUEST_FAILED', response.status);
  }
  if (response.status === 204) return null;
  try {
    return await (cleanPath === 'speak' ? response.blob() : response.json());
  } catch (error) {
    if (error?.name === 'AbortError' || signal?.aborted) throw error;
    throw apiError('The server returned an unreadable response. Please retry.', 'INVALID_RESPONSE', response.status);
  }
}

const action = async (id, name, requestId, signal, extra = {}) =>
  request(sessionPath(id, name), { data: { requestId, ...extra }, signal });

export const api = {
  config: signal => request('config', { signal }),
  create: (context, requestId, signal) => request('practice', { data: { context, requestId }, signal }),
  answer: (id, text, requestId, signal) => action(id, 'answer', requestId, signal, { text }),
  advance: (id, requestId, signal) => action(id, 'advance', requestId, signal),
  finish: (id, requestId, signal) => action(id, 'finish', requestId, signal),
  retry: (id, requestId, signal) => action(id, 'retry', requestId, signal),
  stop: async id => request(sessionPath(id, 'stop'), { method: 'POST', keepalive: true }),
  reset: async id => request(sessionPath(id), { method: 'DELETE', keepalive: true }),
  transcribe: (audio, signal) => request('transcribe', { audio, signal }),
  speak: (text, signal) => request('speak', { data: { text }, signal }),
  segments: async (text, signal) => {
    const result = await request('speech/segments', { data: { text }, signal });
    if (!Array.isArray(result?.segments)) {
      throw apiError('The server returned an invalid speech segment list.', 'INVALID_RESPONSE');
    }
    return result.segments;
  },
};
