const CACHE = 'dumpguard-v28';
const SHELL = [
  '/', '/index.html', '/styles.css', '/manifest.json', '/es.json', '/icon.png',
  '/js/boot.js', '/js/es.js', '/js/install.js', '/js/core.js', '/js/photo.js', '/js/report.js', '/js/map.js', '/js/gov.js', '/js/translate.js', '/js/nav.js', '/lib/leaflet.js',
];

const offline = () => new Response('DumpGuard is offline. Reconnect and reload.', { status: 503, headers: { 'Content-Type': 'text/plain' } });

const remember = async (req, res) => {
  if (res.status !== 200 || res.type !== 'basic') return;
  const cache = await caches.open(CACHE);
  await cache.put(req, res.clone());
};

self.addEventListener('install', e => {
  e.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await Promise.all(SHELL.map(url => cache.add(url).catch(() => {})));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', e => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/') || req.headers.has('range')) return;

  if (req.mode === 'navigate') {
    e.respondWith((async () => {
      const cache = await caches.open(CACHE);
      const cached = await cache.match('/index.html');
      const network = fetch(req).then(res => {
        remember('/index.html', res.clone()).catch(() => {});
        return res;
      });
      if (!cached) return network.catch(offline);
      const slow = new Promise(resolve => setTimeout(() => resolve(cached), 3000));
      return Promise.race([network, slow]).catch(() => cached);
    })());
    return;
  }

  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const hit = await cache.match(req, { ignoreSearch: true });
    if (hit) {
      if (!url.pathname.startsWith('/lib/')) fetch(req).then(res => remember(req, res)).catch(() => {});
      return hit;
    }
    try {
      const res = await fetch(req);
      remember(req, res.clone()).catch(() => {});
      return res;
    } catch {
      return offline();
    }
  })());
});
