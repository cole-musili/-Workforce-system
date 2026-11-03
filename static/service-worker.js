const CACHE_NAME = "workforce-insights-static-v2";

const STATIC_ASSETS = [
    "/static/css/app.css",
    "/static/images/logo.png",
    "/static/images/pwa-icon-192.png",
    "/static/images/pwa-icon-512.png"
];

self.addEventListener("install", event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(STATIC_ASSETS))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys
                    .filter(key => key.startsWith("workforce-insights-static-") && key !== CACHE_NAME)
                    .map(key => caches.delete(key))
            )
        ).then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", event => {
    const request = event.request;
    const url = new URL(request.url);

    if (request.method !== "GET" || url.origin !== self.location.origin) {
        return;
    }

    if (url.pathname.startsWith("/static/")) {
        event.respondWith(
            caches.match(request).then(cached => {
                return cached || fetch(request);
            })
        );
    }
});
