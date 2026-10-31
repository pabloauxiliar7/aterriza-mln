/* =====================================================================
   Service worker: permite usar la web sin conexión.

   - La «carcasa» (HTML, estilos, código, iconos) se guarda al instalar
     y se sirve desde la memoria del teléfono.
   - Los datos (data/*.json) se piden siempre a internet primero; si no
     hay conexión, se devuelve la última copia guardada.

   Si cambias index.html, estilos.css o app.js, sube el número de VERSION
   para que los teléfonos descarguen la versión nueva.
   ===================================================================== */

const VERSION = "aterriza-v2";
const CARCASA = [
  "./",
  "index.html",
  "estilos.css",
  "app.js",
  "manifest.webmanifest",
  "iconos/icono-180.png",
  "iconos/icono-192.png",
  "iconos/icono-512.png",
];

self.addEventListener("install", (evento) => {
  evento.waitUntil(caches.open(VERSION).then((cache) => cache.addAll(CARCASA)));
  self.skipWaiting();
});

// Borra las copias de versiones anteriores.
self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches.keys()
      .then((claves) => Promise.all(claves.filter((c) => c !== VERSION).map((c) => caches.delete(c))))
      .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (evento) => {
  const url = new URL(evento.request.url);
  if (evento.request.method !== "GET" || url.origin !== location.origin) return;

  if (url.pathname.includes("/data/")) {
    // Datos: primero internet; si falla, la última copia guardada.
    evento.respondWith(
      fetch(evento.request)
        .then((respuesta) => {
          const copia = respuesta.clone();
          caches.open(VERSION).then((cache) => cache.put(url.pathname, copia));
          return respuesta;
        })
        .catch(() => caches.match(url.pathname)));
  } else {
    // Carcasa: primero la copia guardada; si no está, internet.
    evento.respondWith(
      caches.match(evento.request, { ignoreSearch: true })
        .then((guardada) => guardada || fetch(evento.request)));
  }
});
