// Middle Atlas Real Estate service worker — app-shell caching for offline use.
const CACHE = 'atlasre-v1';
const PRECACHE = [
    '/',
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/icons/icon-192.png',
    '/static/manifest.webmanifest'
];

self.addEventListener('install', function (event) {
    event.waitUntil(
        caches.open(CACHE).then(function (cache) {
            return cache.addAll(PRECACHE).catch(function () { /* best effort */ });
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', function (event) {
    event.waitUntil(
        caches.keys().then(function (keys) {
            return Promise.all(keys.filter(function (k) { return k !== CACHE; })
                .map(function (k) { return caches.delete(k); }));
        }).then(function () { return self.clients.claim(); })
    );
});

self.addEventListener('fetch', function (event) {
    const req = event.request;
    if (req.method !== 'GET') return;

    const url = new URL(req.url);
    if (url.origin !== location.origin) return;

    // Stale-while-revalidate: serve from cache, refresh in background.
    event.respondWith(
        caches.match(req).then(function (hit) {
            const refresh = fetch(req).then(function (res) {
                if (res && res.ok) {
                    const copy = res.clone();
                    caches.open(CACHE).then(function (c) { c.put(req, copy); });
                }
                return res;
            }).catch(function () {
                // Offline fallback: cached shell for navigations.
                if (req.mode === 'navigate') return caches.match('/');
                return hit || Response.error();
            });
            return hit || refresh;
        })
    );
});
