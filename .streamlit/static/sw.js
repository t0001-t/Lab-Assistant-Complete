// sw.js – Service Worker für Lab Assistant PWA
// Version: 1.0.9
// Cache-Strategien: Cache-First (Static), Network-First (HTML), Stale-While-Revalidate (API)

const CACHE_VERSION = 'v1.0.9';
const STATIC_CACHE = `lab-assistant-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `lab-assistant-dynamic-${CACHE_VERSION}`;
const OFFLINE_URL = '/static/offline.html';

// Assets die sofort gecacht werden (App Shell)
const STATIC_ASSETS = [
  '/',
  '/static/manifest.json',
  '/pwa-ui.css?v=1.0.9',
  '/pwa-icons.js?v=1.0.9',
  '/pwa-runtime.js?v=1.0.9',
  '/static/offline.html',
  '/static/assets/icon-192.png',
  '/static/assets/icon-512.png',
];

// Install Event – App Shell cachen
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => {
        console.log('[SW] Caching App Shell');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => self.skipWaiting())
  );
});

// Activate Event – Alte Caches löschen
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key !== STATIC_CACHE && key !== DYNAMIC_CACHE)
          .map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

// Fetch Event – Cache-Strategien
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') return;

  // Skip non-HTTP(S) URLs
  if (!url.protocol.startsWith('http')) return;

  // Streamlit WebSocket/Internal nicht cachen
  if (url.pathname.includes('/_stcore/stream') ||
      url.pathname.includes('/_stcore/health') ||
      url.pathname.includes('/_stcore/host-config') ||
      url.pathname.includes('/_stcore/message') ||
      url.pathname.includes('/_stcore/browser-check') ||
      url.pathname.includes('/_stcore/allowed-message-origins')) {
    return;
  }

  // Static Assets – Cache First
  if (STATIC_ASSETS.some(asset => url.pathname === asset) ||
      url.pathname.startsWith('/static/assets/') ||
      url.pathname.endsWith('.png') ||
      url.pathname.endsWith('.ico') ||
      url.pathname.endsWith('.css') ||
      url.pathname.endsWith('.js') ||
      url.pathname.endsWith('.woff') ||
      url.pathname.endsWith('.woff2') ||
      url.pathname === '/static/manifest.json') {
    event.respondWith(cacheFirst(request));
    return;
  }

  // HTML/Navigation – Network First mit Offline-Fallback
  if (request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(networkFirstWithOffline(request));
    return;
  }

  // API/JSON/Data – Stale While Revalidate
  event.respondWith(staleWhileRevalidate(request));
});

// Cache-First Strategy
async function cacheFirst(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('Offline', { status: 503, statusText: 'Service Unavailable' });
  }
}

// Network-First mit Offline-Fallback
async function networkFirstWithOffline(request) {
  const cache = await caches.open(DYNAMIC_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await cache.match(request);
    if (cached) return cached;
    const offlineCache = await caches.open(STATIC_CACHE);
    return offlineCache.match('/static/offline.html');
  }
}

// Stale-While-Revalidate
async function staleWhileRevalidate(request) {
  const cache = await caches.open(DYNAMIC_CACHE);
  const cached = await cache.match(request);

  const fetchPromise = fetch(request)
    .then((response) => {
      if (response.ok) {
        cache.put(request, response.clone());
      }
      return response;
    })
    .catch(() => cached);

  return cached || fetchPromise;
}

// Background Sync für To-Do Sync
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-todos') {
    event.waitUntil(syncTodos());
  }
});

async function syncTodos() {
  console.log('[SW] Background sync: todos');
  // To-Do Sync Logik hier implementieren
  // z.B. IndexedDB → Server sync
}

// Push Notifications (optional)
self.addEventListener('push', (event) => {
  if (!event.data) return;
  const data = event.data.json();
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/static/assets/icon-192.png',
      badge: '/static/assets/icon-72.png',
      data: { url: data.url || '/' },
      vibrate: [100, 50, 100],
      requireInteraction: true
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url === event.notification.data.url && 'focus' in client) {
          return client.focus();
        }
      }
      return clients.openWindow(event.notification.data.url);
    })
  );
});

// Periodic Background Sync (wenn unterstützt)
self.addEventListener('periodicsync', (event) => {
  if (event.tag === 'periodic-todo-sync') {
    event.waitUntil(syncTodos());
  }
});

// Message Handler für Kommunikation mit Hauptthread
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  if (event.data && event.data.type === 'GET_VERSION') {
    event.ports[0].postMessage({ version: CACHE_VERSION });
  }
});
