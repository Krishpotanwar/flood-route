const CACHE_PREFIX = `floodroute-${self.registration.scope}-`;
const CACHE_NAME = `${CACHE_PREFIX}v4`;
const STATIC_ASSETS = ["./", "./index.html", "./manifest.webmanifest", "./icons/floodroute.svg"]
  .map((path) => new URL(path, self.registration.scope).href);
const SHELL_URL = new URL("./index.html", self.registration.scope).href;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k.startsWith(CACHE_PREFIX) && k !== CACHE_NAME)
          .map((k) => caches.delete(k))
      );
    })
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  // Let the browser honor the map provider's HTTP cache headers.
  if (url.hostname === "tile.openstreetmap.org") return;
  // Evidence photos never enter the public offline cache.
  if (url.pathname.startsWith("/v1/reports/photo/")) return;

  // Navigation fallback: serve the cached app shell when offline so the
  // PWA boots. Hashed JS/CSS bundles are cached on first visit by the
  // cache-first branch below; true install-time precache of hashed
  // bundle names needs build-time injection (parked).
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(() =>
        caches.match(SHELL_URL)
      )
    );
    return;
  }

  // Stale-while-revalidate for CDN snapshots and city catalog
  if (
    url.pathname.startsWith("/v1/feed/snapshot/closures") ||
    url.pathname.startsWith("/v1/cities")
  ) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        const fetchPromise = fetch(event.request)
          .then((response) => {
            if (response && response.status === 200) {
              const clone = response.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
            }
            return response;
          })
          .catch(() => cached);

        return cached || fetchPromise;
      })
    );
    return;
  }

  // Network-first for other API requests (route, reroute, health)
  if (url.pathname.startsWith("/v1/")) {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request))
    );
    return;
  }

  // Cache-first for static shell assets and map tile assets
  event.respondWith(
    caches.match(event.request).then((cached) => {
      return (
        cached ||
        fetch(event.request).then((response) => {
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        })
      );
    })
  );
});

// Background Sync API listener for offline crowd reports
self.addEventListener("sync", (event) => {
  if (event.tag === "floodroute-sync-reports") {
    event.waitUntil(
      self.clients.matchAll().then((clients) => {
        clients.forEach((client) => {
          client.postMessage({ type: "FLUSH_OFFLINE_REPORTS" });
        });
      })
    );
  }
});
