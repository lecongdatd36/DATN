(() => {
  const root = document.querySelector("[data-live-workspace]");
  if (!root?.dataset.stateUrl) return;

  const normalDelay = 3500;
  let retryDelay = normalDelay;
  let signature = null;
  let etag = null;
  let initialized = false;
  let timer = null;
  let controller = null;
  let mutationReset = false;
  let suspended = false;
  let busyCount = 0;
  let eventSource = null;

  const liveBadge = root.querySelector(".sales-live") || document.querySelector(".sales-live");

  const updateLiveIndicator = (mode) => {
    if (!liveBadge) return;
    if (mode === "sse") {
      liveBadge.innerHTML = `<span aria-hidden="true" style="background:#10b981;box-shadow:0 0 0 .25rem rgba(16,185,129,.2)"></span>Thời gian thực (SSE)`;
      liveBadge.classList.add("is-sse-connected");
    } else {
      liveBadge.innerHTML = `<span aria-hidden="true"></span>Tự cập nhật mỗi 3.5 giây`;
      liveBadge.classList.remove("is-sse-connected");
    }
  };

  const schedule = (delay = normalDelay) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(poll, delay);
  };

  const poll = async () => {
    mutationReset = false;
    if (suspended) return;
    if (document.hidden) {
      // Khi tab chạy ngầm, giãn chu kỳ sang 6s nhưng vẫn tiếp tục poll
      schedule(6000);
    }

    controller?.abort();
    controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 6000);
    const headers = {"X-Requested-With": "XMLHttpRequest"};
    if (etag) headers["If-None-Match"] = etag;

    try {
      const response = await fetch(root.dataset.stateUrl, {
        headers,
        cache: "no-store",
        credentials: "same-origin",
        signal: controller.signal,
      });
      window.clearTimeout(timeout);

      if (response.status === 304) {
        retryDelay = normalDelay;
        schedule();
        return;
      }
      if (!response.ok) throw new Error(`Polling HTTP ${response.status}`);

      const nextEtag = response.headers.get("ETag");
      const text = await response.text();
      let payload = null;
      try {
        payload = JSON.parse(text);
      } catch (_) {}

      const nextSignature = nextEtag || text;
      if (initialized && signature !== nextSignature) {
        document.dispatchEvent(new CustomEvent("workspace:state-change", { detail: payload }));
      }

      initialized = true;
      signature = nextSignature;
      etag = nextEtag;
      retryDelay = normalDelay;
      schedule();
    } catch (error) {
      window.clearTimeout(timeout);
      if (error.name === "AbortError" && (mutationReset || suspended)) return;
      if (error.name !== "AbortError") retryDelay = Math.min(retryDelay * 2, 30000);
      schedule(retryDelay);
    }
  };

  // Thiết lập Server-Sent Events (SSE) nếu có streamUrl
  const startSSE = () => {
    const streamUrl = root.dataset.streamUrl;
    if (!streamUrl || typeof window.EventSource === "undefined") {
      updateLiveIndicator("poll");
      poll();
      return;
    }

    try {
      eventSource = new EventSource(streamUrl);

      eventSource.onopen = () => {
        updateLiveIndicator("sse");
      };

      eventSource.onmessage = (event) => {
        if (!event.data) return;
        try {
          const payload = JSON.parse(event.data);
          const nextSignature = JSON.stringify(payload);
          if (initialized && signature !== nextSignature) {
            document.dispatchEvent(new CustomEvent("workspace:state-change", { detail: payload }));
          }
          initialized = true;
          signature = nextSignature;
        } catch (err) {
          console.warn("[QLNH Realtime] Lỗi đọc dữ liệu SSE:", err);
        }
      };

      eventSource.onerror = () => {
        // SSE bị ngắt, đóng và chuyển sang polling dự phòng
        if (eventSource) {
          eventSource.close();
          eventSource = null;
        }
        updateLiveIndicator("poll");
        schedule(1500);
      };
    } catch (err) {
      console.warn("[QLNH Realtime] Không thể kết nối SSE, dùng polling dự phòng:", err);
      updateLiveIndicator("poll");
      poll();
      return;
    }

    // Luôn chạy song song một polling heartbeat nhẹ mỗi 4 giây để bảo đảm không bị nghẽn
    schedule(4000);
  };

  document.addEventListener("workspace:mutation", () => {
    mutationReset = true;
    controller?.abort();
    initialized = false;
    signature = null;
    etag = null;
    retryDelay = normalDelay;
    schedule(250);
  });

  document.addEventListener("workspace:busy", (event) => {
    busyCount = event.detail ? busyCount + 1 : Math.max(0, busyCount - 1);
    suspended = busyCount > 0;
    if (suspended) {
      window.clearTimeout(timer);
      controller?.abort();
    } else {
      schedule(250);
    }
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      if (!eventSource && root.dataset.streamUrl) {
        startSSE();
      } else {
        schedule(100);
      }
    }
  });

  // Khởi động SSE ưu tiên, tự động fallback về Polling
  startSSE();
})();
