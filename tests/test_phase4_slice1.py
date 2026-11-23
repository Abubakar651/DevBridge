import json
from pathlib import Path
import subprocess

import httpx
import pytest

from server.app import create_app
from tests.test_phase3_slice1 import TEST_SETTINGS

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_manifest_icons_and_sw_served_with_pwa_contract():
    html = source("web/index.html")
    assert '<link rel="manifest" href="/manifest.webmanifest">' in html
    assert '<link rel="apple-touch-icon" href="/icon-maskable.svg">' in html
    assert '<meta name="apple-mobile-web-app-capable" content="yes">' in html
    assert '<meta name="mobile-web-app-capable" content="yes">' in html

    app = create_app(settings_loader=lambda: TEST_SETTINGS)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:4317") as client:
        manifest_res = await client.get("/manifest.webmanifest")
        assert manifest_res.status_code == 200
        assert "application/manifest+json" in manifest_res.headers.get("content-type", "")
        manifest = json.loads(manifest_res.text)
        assert manifest["short_name"] == "DevBridge"
        assert manifest["display"] == "standalone"
        assert manifest["start_url"] == "/"
        purposes = {icon["purpose"] for icon in manifest["icons"]}
        assert {"any", "maskable"} <= purposes

        maskable_res = await client.get("/icon-maskable.svg")
        assert maskable_res.status_code == 200
        assert "<svg" in maskable_res.text

        sw_res = await client.get("/sw.js")
        assert sw_res.status_code == 200
        assert "devbridge-shell-v1" in sw_res.text


def test_service_worker_caches_static_shell_only_and_never_caches_api_requests():
    script = """
    import assert from 'node:assert/strict';
    import fs from 'node:fs';
    import vm from 'node:vm';

    const listeners = {};
    const cacheData = new Map();
    const cachesStore = new Map([
      ['old-cache-v0', new Map()],
    ]);

    const fakeCaches = {
      async open(name) {
        if (!cachesStore.has(name)) cachesStore.set(name, cacheData);
        const store = cachesStore.get(name);
        return {
          async addAll(urls) {
            for (const u of urls) store.set(u, { status: 200, body: `cached:${u}` });
          },
          async put(req, res) {
            const path = new URL(req.url, 'http://127.0.0.1:4317').pathname;
            store.set(path, res);
          },
        };
      },
      async keys() {
        return Array.from(cachesStore.keys());
      },
      async delete(name) {
        return cachesStore.delete(name);
      },
      async match(req) {
        const path = typeof req === 'string' ? req : new URL(req.url, 'http://127.0.0.1:4317').pathname;
        return cacheData.get(path) || null;
      },
    };

    let online = true;
    const context = {
      self: {
        location: { origin: 'http://127.0.0.1:4317' },
        addEventListener(type, fn) { listeners[type] = fn; },
        skipWaiting() {},
        clients: { claim() {} },
      },
      caches: fakeCaches,
      URL,
      Response: class {
        constructor(body, init = {}) { this.body = body; this.status = init.status || 200; this.headers = init.headers || {}; }
        clone() { return new context.Response(this.body, { status: this.status, headers: this.headers }); }
      },
      fetch: async req => {
        if (!online) throw new Error('Network offline');
        const path = new URL(req.url, 'http://127.0.0.1:4317').pathname;
        return new context.Response(`live:${path}`, { status: 200 });
      },
    };
    context.globalThis = context;
    vm.createContext(context);
    vm.runInContext(fs.readFileSync('./web/sw.js', 'utf8'), context);

    const { CACHE_NAME, STATIC_SHELL, isStaticShellRequest } = context.__DEVBRIDGE_SW__;
    assert.equal(CACHE_NAME, 'devbridge-shell-v1');
    assert.ok(STATIC_SHELL.includes('/'));
    assert.ok(STATIC_SHELL.includes('/manifest.webmanifest'));

    // 1. Install caches static shell; Activate deletes old caches.
    let installPromise;
    listeners.install({ waitUntil(p) { installPromise = p; } });
    await installPromise;
    assert.equal(cacheData.size, STATIC_SHELL.length);

    let activatePromise;
    listeners.activate({ waitUntil(p) { activatePromise = p; } });
    await activatePromise;
    assert.equal(cachesStore.has('old-cache-v0'), false);
    assert.equal(cachesStore.has('devbridge-shell-v1'), true);

    // 2. /api/* and non-GET requests are strictly ignored by the service worker.
    for (const apiReq of [
      { method: 'GET', url: 'http://127.0.0.1:4317/api/config', mode: 'cors' },
      { method: 'POST', url: 'http://127.0.0.1:4317/api/practice', mode: 'cors' },
      { method: 'POST', url: 'http://127.0.0.1:4317/api/speak', mode: 'cors' },
      { method: 'POST', url: 'http://127.0.0.1:4317/api/transcribe', mode: 'cors' },
      { method: 'GET', url: 'https://api.groq.com/openai/v1/audio/speech', mode: 'cors' },
    ]) {
      assert.equal(isStaticShellRequest(apiReq, 'http://127.0.0.1:4317'), false);
      let intercepted = false;
      listeners.fetch({ request: apiReq, respondWith() { intercepted = true; } });
      assert.equal(intercepted, false);
    }

    // 3. Static shell requests use network when online and fall back to cache when offline.
    let shellPromise;
    listeners.fetch({
      request: { method: 'GET', url: 'http://127.0.0.1:4317/styles.css', mode: 'same-origin' },
      respondWith(p) { shellPromise = p; },
    });
    const liveRes = await shellPromise;
    assert.equal(liveRes.body, 'live:/styles.css');

    online = false;
    let offlinePromise;
    listeners.fetch({
      request: { method: 'GET', url: 'http://127.0.0.1:4317/styles.css', mode: 'same-origin' },
      respondWith(p) { offlinePromise = p; },
    });
    const cachedRes = await offlinePromise;
    assert.equal(cachedRes.body, 'live:/styles.css');
    """
    result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=PROJECT_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
