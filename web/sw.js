// Static-shell-only service worker. Cloud and /api/* requests are never cached.
const CACHE_NAME = 'devbridge-shell-v1';
const STATIC_SHELL = [
  '/',
  '/index.html',
  '/styles.css',
  '/app.js',
  '/api.js',
  '/audio.js',
  '/session.js',
  '/icon.svg',
  '/icon-maskable.svg',
  '/manifest.webmanifest',
];

function isStaticShellRequest(request, origin = self.location?.origin) {
  if (!request || request.method !== 'GET') return false;
  let url;
  try {
    url = new URL(request.url, origin || 'http://127.0.0.1');
  } catch {
    return false;
  }
  if (origin && url.origin !== origin) return false;
  if (url.pathname === '/api' || url.pathname.startsWith('/api/')) return false;
  return request.mode === 'navigate' || STATIC_SHELL.includes(url.pathname);
}

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(STATIC_SHELL))
      .then(() => self.skipWaiting?.()),
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))))
      .then(() => self.clients?.claim?.()),
  );
});

self.addEventListener('fetch', event => {
  const { request } = event;
  if (!isStaticShellRequest(request)) return;
  event.respondWith(
    fetch(request)
      .then(response => {
        if (response && response.status === 200) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, copy)).catch(() => {});
        }
        return response;
      })
      .catch(async () => {
        const cached = await caches.match(request);
        if (cached) return cached;
        if (request.mode === 'navigate') {
          const root = await caches.match('/');
          if (root) return root;
        }
        return new Response('DevBridge is offline. Reconnect to start a live practice session.', {
          status: 503,
          headers: { 'Content-Type': 'text/plain; charset=utf-8' },
        });
      }),
  );
});

globalThis.__DEVBRIDGE_SW__ = { CACHE_NAME, STATIC_SHELL, isStaticShellRequest };
