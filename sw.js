const CACHE_NAME = 'stock-reminder-v6'; // 升級至 v6 激活全新智慧路由分流
const ASSETS = [
  './',
  './index.html',
  './manifest.json'
];

// 安裝事件：快取基礎靜態資源
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      console.log('[Service Worker] 下載最新 v6 核心靜態快取...');
      return cache.addAll(ASSETS);
    })
  );
  self.skipWaiting();
});

// 激活事件：全面清除舊版本快取
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.map(key => {
          if (key !== CACHE_NAME) {
            console.log('[Service Worker] 刪除舊過期快取:', key);
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// 攔截請求：高階智慧型路由分流策略
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // ⚡ 策略 A：動態股票數據與圖表 —— 嚴格執行「純網路模式（Network-Only）」
  // 納入核心 `./stock_data.json`，確保數據絕不進快取，100% 抓到雲端最新報價
  if (
    url.pathname.includes('stock_data.json') || 
    url.hostname.includes('finnhub.io') || 
    url.hostname.includes('tradingview.com')
  ) {
    event.respondWith(
      fetch(event.request).catch(err => {
        console.warn(`[SW] 數據請求失敗，當前處於離線狀態: ${url.pathname}`);
        // 如果 stock_data.json 意外斷網，嘗試從快取當作備份吐出（防崩潰防線）
        return caches.match(event.request);
      })
    );
    return;
  }

  // ⚡ 策略 B：核心 UI 骨架 (index.html / 根目錄) —— 「網路優先 (Network-First)」
  // 有網路必然拿最新版並無感更新快取；斷網時秒切離線快取，保障 PWA 正常運作
  if (event.request.mode === 'navigate' || url.pathname.endsWith('index.html') || url.pathname === '/') {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          if (response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          }
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // ⚡ 策略 C：靜態資源 (manifest, icon, css) —— 「亞穩態後台更新 (Stale-While-Revalidate)」
  // 這是最專業的 PWA 策略：先用快取達成 0.1 秒極速開網頁，同時後台默默去下載新版，下次開啟時自動生效
  event.respondWith(
    caches.match(event.request).then(cachedResponse => {
      const fetchPromise = fetch(event.request).then(networkResponse => {
        if (networkResponse.status === 200) {
          const clone = networkResponse.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return networkResponse;
      }).catch(() => null); // 忽略背景抓取失敗

      return cachedResponse || fetchPromise;
    })
  );
});
