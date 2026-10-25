/* ЛАКОРНИЯ · МЕГАМЕТАПЛЕЕР — сервис-воркер такта M5 «МАГНЕТИЗМ».
   Задача: «Соединение сброшено» больше не отшибает дверь —
   сборка живёт в кэше; при живой сети тихо обновляется фоном. */
const VER = "lakornia-m5-2026-10-25";
const SHELL = ["./", "./index.html", "./manifest.webmanifest", "./icon-192.png", "./icon-512.png", "./vendor/webtorrent.min.js"];

self.addEventListener("install", e => {
  e.waitUntil(
    /* каждый файл — отдельной ставкой: одна осечка не валит всю установку */
    caches.open(VER).then(c => Promise.allSettled(SHELL.map(u => c.add(u)))).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(ks => Promise.all(ks.filter(k => k !== VER).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

/* Переводчики и P2P-статистика кэшу не подлежат — только сеть */
const NET_ONLY = /mymemory\.translated\.net|translate\.googleapis\.com|\/api\/torrent|\/api\/nnm/i;

self.addEventListener("fetch", e => {
  const req = e.request;
  if(req.method !== "GET") return;
  let url;
  try{ url = new URL(req.url); }catch(err){ return; }
  if(NET_ONLY.test(url.href)) return;

  /* Навигация: сеть первой — кэш как страховка от сброса соединения */
  if(req.mode === "navigate"){
    e.respondWith(
      fetch(req).then(r => {
        if(r && r.ok){
          const cp = r.clone();
          caches.open(VER).then(c => c.put("./index.html", cp)).catch(() => {});
        }
        return r;
      }).catch(() =>
        caches.match(req).then(mine => mine || caches.match("./index.html") || caches.match("./") || Response.error())
      )
    );
    return;
  }

  /* Статика и CDN: кэш первой, обновление фоном (stale-while-revalidate) */
  e.respondWith(
    caches.match(req).then(hit => {
      const net = fetch(req).then(r => {
        if(r && (r.ok || r.type === "opaque")){
          const cp = r.clone();
          caches.open(VER).then(c => c.put(req, cp)).catch(() => {});
        }
        return r;
      }).catch(() => hit);
      return hit || net;
    })
  );
});
