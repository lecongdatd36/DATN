(() => {
  "use strict";
  const root = document.querySelector("[data-notification-url]");
  if (!root) return;
  let timer, controller, stopped = false, etag = null, delay = 5000, refreshRequested = false;
  const emitStatus = state => document.dispatchEvent(new CustomEvent("notifications:status", {detail: state}));
  const render = payload => {
    const {counts, entries} = payload;
    const values = {...counts};
    entries.forEach(entry => { values[entry.key] = entry.count; });
    document.querySelectorAll("[data-notification-items]").forEach(container => {
      const allowed = new Set(entries.map(entry => entry.key));
      [...container.querySelectorAll("[data-notification-entry]")].forEach(link => {
        if (!allowed.has(link.dataset.notificationEntry)) link.remove();
      });
      entries.forEach(entry => {
        const url = new URL(entry.url, location.origin);
        if (url.origin !== location.origin || !["http:", "https:"].includes(url.protocol)) return;
        let link = [...container.querySelectorAll("[data-notification-entry]")].find(node => node.dataset.notificationEntry === entry.key);
        if (!link) {
          link = document.createElement("a"); link.className = "notification-entry";
          link.dataset.notificationEntry = entry.key;
          link.append(document.createElement("span"));
          const badge = document.createElement("span"); badge.className = "nav-notification-badge";
          badge.dataset.notificationCount = entry.key; link.append(badge); container.append(link);
        }
        link.querySelector("span").textContent = entry.label; link.href = url.href;
        if (container.dataset.notificationItems === "mobile" && url.pathname === root.dataset.mobileUrl) link.setAttribute("data-mobile-link", "");
        else link.removeAttribute("data-mobile-link");
      });
    });
    document.querySelectorAll("[data-notification-count]").forEach(badge => {
      const count = values[badge.dataset.notificationCount] || 0;
      badge.textContent = count > 99 ? "99+" : String(count); badge.hidden = count === 0;
      badge.setAttribute("aria-label", count + " việc đang chờ");
    });
    document.querySelectorAll("[data-notification-entry]").forEach(link => { link.hidden = !values[link.dataset.notificationEntry]; });
    document.querySelectorAll("[data-notification-total]").forEach(node => { node.textContent = String(counts.total); });
    document.querySelectorAll("[data-notification-empty]").forEach(node => { node.hidden = counts.total > 0; });
    document.dispatchEvent(new CustomEvent("notifications:updated", {detail: payload}));
  };
  const schedule = () => {
    clearTimeout(timer);
    if (!stopped && !document.hidden) timer = setTimeout(poll, delay);
  };
  const poll = async () => {
    if (stopped || document.hidden || controller) return;
    controller = new AbortController();
    const timeout = setTimeout(() => controller?.abort(), 6000);
    try {
      const headers = {"X-Requested-With": "XMLHttpRequest"};
      if (etag) headers["If-None-Match"] = etag;
      const response = await fetch(root.dataset.notificationUrl, {headers, credentials: "same-origin", cache: "no-store", signal: controller.signal});
      if (response.redirected || response.status === 401 || response.status === 403) {
        stopped = true; render({counts: {total: 0}, entries: []}); emitStatus("expired"); return;
      }
      if (response.status !== 304) {
        if (!response.ok) throw new Error("Notification request failed");
        const payload = await response.json();
        if (!payload.counts || !Array.isArray(payload.entries) || !Number.isInteger(payload.counts.total) || payload.entries.some(entry => typeof entry.key !== "string" || typeof entry.label !== "string" || !Number.isInteger(entry.count) || entry.count < 0)) throw new Error("Invalid notification state");
        if (refreshRequested) return;
        render(payload); etag = response.headers.get("ETag");
      }
      delay = 5000; emitStatus("online");
    } catch (_) { if (!refreshRequested && !document.hidden) { delay = Math.min(delay * 2, 60000); emitStatus("offline"); } }
    finally {
      clearTimeout(timeout); controller = null;
      if (refreshRequested && !stopped && !document.hidden) { refreshRequested = false; etag = null; poll(); }
      else schedule();
    }
  };
  document.addEventListener("mobile:page-ready", () => {
    // Keep the new page's fresh server counts; never overwrite them with an old snapshot.
    clearTimeout(timer); etag = null;
    if (controller) { refreshRequested = true; controller.abort(); }
    else poll();
  });
  document.addEventListener("visibilitychange", () => {
    clearTimeout(timer);
    if (document.hidden) controller?.abort();
    else if (!stopped) { etag = null; poll(); }
  });
  window.addEventListener("pagehide", () => { stopped = true; clearTimeout(timer); controller?.abort(); });
  window.addEventListener("pageshow", event => { if (event.persisted) { stopped = false; etag = null; poll(); } });
  poll();
})();
