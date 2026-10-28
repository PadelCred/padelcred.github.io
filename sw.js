// PadelCred offline support. Change the version when you update the app.
const VERSION = 'padelcred-v146';
const SHELL = ['./', 'manifest.json', 'icon-192.png', 'icon-512.png', 'apple-touch-icon.png', 'icon-maskable-512.png', 'favicon-64.png'];

self.addEventListener('install', e => {
  // Save each file on its own, so one failure (a redirect, a slow connection) can never stop the app installing.
  e.waitUntil(caches.open(VERSION).then(c => Promise.all(SHELL.map(u => c.add(u).catch(() => null)))).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  // Only handle normal web addresses: browser extensions and other schemes are left alone.
  if (!/^https?:/.test(e.request.url)) return;
  // Live lookups (venue search, accounts and sync) always go straight to the network.
  if (/photon\.komoot\.io|firestore\.googleapis|identitytoolkit|securetoken|googleapis\.com\/identity/.test(e.request.url)) return;
  // Pages: try the network first so updates come through, fall back to the saved copy offline.
  if (e.request.mode === 'navigate') {
    e.respondWith(fetch(e.request)
      .then(r => { const copy = r.clone(); caches.open(VERSION).then(c => c.put('./', copy)); return r; })
      .catch(() => caches.match('./')));
    return;
  }
  // Everything else (icons, fonts): saved copy first, then network.
  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request).then(r => {
    if (r.ok || r.type === 'opaque') { const copy = r.clone(); caches.open(VERSION).then(c => c.put(e.request, copy)); }
    return r;
  })));
});
