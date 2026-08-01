const IMAGE_CACHE = 'alive-image-cache-v1';

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET' || request.destination !== 'image') return;

  event.respondWith((async () => {
    const cache = await caches.open(IMAGE_CACHE);
    const cached = await cache.match(request);
    if (cached) return cached;

    const response = await fetch(request);
    // Cross-origin backgrounds are opaque responses. They are still safe to
    // store and replay in the browser cache without reading their contents.
    if (response.ok || response.type === 'opaque') {
      cache.put(request, response.clone()).catch(() => undefined);
    }
    return response;
  })());
});
