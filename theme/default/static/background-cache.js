const IMAGE_CACHE = 'alive-image-cache-v1';

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);
  const isSiteIcon = url.origin === self.location.origin && url.pathname === '/favicon.ico';
  if (request.method !== 'GET' || (request.destination !== 'image' && !isSiteIcon)) return;

  event.respondWith((async () => {
    const cache = await caches.open(IMAGE_CACHE);
    const cached = await cache.match(request);
    if (cached) return cached;

    const response = await fetch(request);
    // Cross-origin backgrounds are opaque responses. They are still safe to
    // store and replay in the browser cache without reading their contents.
    // The explicit favicon branch keeps page switches from re-downloading the
    // versioned browser icon on engines that do not classify it as an image.
    if (response.ok || response.type === 'opaque') {
      cache.put(request, response.clone()).catch(() => undefined);
    }
    return response;
  })());
});
