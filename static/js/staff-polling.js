(() => {
  const root = document.querySelector("[data-live-workspace]");
  if (!root?.dataset.stateUrl) return;

  // Polling is deliberately used instead of a database-polled SSE stream.
  // A regular ETag request is inexpensive for this project and, unlike a
  // long-lived synchronous stream, does not reserve a web worker per screen.
  // Staff need to see a new order promptly, while background tabs still
  // remain inexpensive for the database and the device battery.
  const foregroundDelay = 3000;
  const requestTimeout = 6000;
  const maxRetryDelay = 60000;
  let retryDelay = foregroundDelay;
  let signature = null;
  let etag = null;
  let initialized = false;
  let timer = null;
  let controller = null;
  let suspended = false;
  let busyCount = 0;
  let isPolling = false;

  const liveBadge = root.querySelector(".sales-live") || document.querySelector(".sales-live");

  const currentDelay = () => foregroundDelay;

  const updateLiveIndicator = () => {
    if (!liveBadge) return;
    const seconds = currentDelay() / 1000;
    liveBadge.innerHTML = `<span aria-hidden="true"></span>Tự cập nhật mỗi ${seconds} giây`;
    liveBadge.classList.remove("is-sse-connected");
  };

  const schedule = (delay = currentDelay()) => {
    window.clearTimeout(timer);
    if (suspended || document.hidden) return;
    timer = window.setTimeout(poll, delay);
  };

  const poll = async () => {
    if (suspended || document.hidden) return;
    if (isPolling) {
      schedule(250);
      return;
    }
    isPolling = true;

    const requestController = new AbortController();
    controller = requestController;
    let timedOut = false;
    let scheduleAfterRequest = true;
    const timeout = window.setTimeout(() => {
      timedOut = true;
      requestController.abort();
    }, requestTimeout);
    const headers = {"X-Requested-With": "XMLHttpRequest"};
    if (etag) headers["If-None-Match"] = etag;

    try {
      const response = await fetch(root.dataset.stateUrl, {
        headers,
        cache: "no-store",
        credentials: "same-origin",
        signal: requestController.signal,
      });

      if (response.status === 304) {
        retryDelay = currentDelay();
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
      if (!initialized && payload) {
        // Consumers that load after this request can still read the baseline
        // from the workspace element.  This lets the first new QR/payment
        // request be recognised as a notification instead of a baseline.
        root.__qlnhLiveState = payload;
        document.dispatchEvent(new CustomEvent("workspace:state-ready", { detail: payload }));
      } else if (initialized && signature !== nextSignature) {
        root.__qlnhLiveState = payload;
        document.dispatchEvent(new CustomEvent("workspace:state-change", { detail: payload }));
      }

      initialized = true;
      signature = nextSignature;
      etag = nextEtag;
      retryDelay = currentDelay();
    } catch (error) {
      // An abort triggered by a user action, a modal, or a visibility change
      // is already followed by an explicit schedule in that event handler.
      if (error.name === "AbortError" && !timedOut) {
        scheduleAfterRequest = false;
        return;
      }
      retryDelay = Math.min(Math.max(retryDelay * 2, foregroundDelay), maxRetryDelay);
    } finally {
      window.clearTimeout(timeout);
      if (controller === requestController) controller = null;
      isPolling = false;
      if (scheduleAfterRequest) schedule(retryDelay);
    }
  };

  document.addEventListener("workspace:mutation", () => {
    controller?.abort();
    retryDelay = foregroundDelay;
    schedule(250);
  });

  document.addEventListener("workspace:busy", (event) => {
    busyCount = event.detail ? busyCount + 1 : Math.max(0, busyCount - 1);
    suspended = busyCount > 0;
    if (suspended) {
      window.clearTimeout(timer);
      controller?.abort();
    } else {
      retryDelay = currentDelay();
      schedule(250);
    }
  });

  document.addEventListener("visibilitychange", () => {
    updateLiveIndicator();
    controller?.abort();
    retryDelay = currentDelay();
    schedule(100);
  });

  updateLiveIndicator();
  poll();
})();
