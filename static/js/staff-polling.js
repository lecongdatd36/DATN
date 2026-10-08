(() => {
  const root = document.querySelector("[data-live-workspace]");
  if (!root?.dataset.stateUrl) return;

  const normalDelay = 10000;
  let retryDelay = normalDelay;
  let signature = null;
  let etag = null;
  let initialized = false;
  let timer = null;
  let controller = null;
  let mutationReset = false;
  let suspended = false;
  let busyCount = 0;

  const schedule = (delay = normalDelay) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(poll, delay);
  };

  const poll = async () => {
    mutationReset = false;
    if (suspended) return;
    if (document.hidden) {
      schedule(30000);
      return;
    }

    controller?.abort();
    controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 8000);
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
      const nextSignature = nextEtag || await response.text();
      if (initialized && signature !== nextSignature) {
        window.location.reload();
        return;
      }

      initialized = true;
      signature = nextSignature;
      etag = nextEtag;
      retryDelay = normalDelay;
      schedule();
    } catch (error) {
      window.clearTimeout(timeout);
      if (error.name === "AbortError" && (mutationReset || suspended)) return;
      if (error.name !== "AbortError") retryDelay = Math.min(retryDelay * 2, 60000);
      schedule(retryDelay);
    }
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
    if (!document.hidden) schedule(100);
  });

  poll();
})();
