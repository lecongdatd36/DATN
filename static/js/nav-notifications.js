(() => {
  const root = document.querySelector('[data-notification-url]');
  if (!root) return;
  let timer;
  let controller;
  let stopped = false;
  let etag = null;
  let delay = 5000;

  const render = ({counts, entries}) => {
    const values = {...counts};
    entries.forEach(entry => { values[entry.key] = entry.count; });
    // Mobile navigation can replace its DOM without reloading the document.
    document.querySelectorAll('[data-notification-count]').forEach(badge => {
      const count = values[badge.dataset.notificationCount] || 0;
      badge.textContent = String(count);
      badge.hidden = count === 0;
      badge.setAttribute('aria-label', `${count} việc đang chờ`);
    });
    document.querySelectorAll('[data-notification-entry]').forEach(entry => {
      entry.hidden = !values[entry.dataset.notificationEntry];
    });
    document.querySelectorAll('[data-notification-total]').forEach(node => { node.textContent = String(counts.total); });
    document.querySelectorAll('[data-notification-empty]').forEach(node => { node.hidden = counts.total > 0; });
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
      const headers = {'X-Requested-With': 'XMLHttpRequest'};
      if (etag) headers['If-None-Match'] = etag;
      const response = await fetch(root.dataset.notificationUrl, {
        headers, credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
      });
      if (response.redirected || response.status === 401 || response.status === 403) {
        stopped = true;
        return;
      }
      if (response.status !== 304) {
        if (!response.ok) throw new Error('Notification request failed');
        render(await response.json());
        etag = response.headers.get('ETag');
      }
      delay = 5000;
    } catch (_) {
      delay = Math.min(delay * 2, 60000);
    } finally {
      clearTimeout(timeout);
      controller = null;
      schedule();
    }
  };
  document.addEventListener('visibilitychange', () => {
    clearTimeout(timer);
    if (document.hidden) controller?.abort();
    else if (!stopped) { etag = null; poll(); }
  });
  window.addEventListener('pagehide', () => { stopped = true; clearTimeout(timer); controller?.abort(); });
  window.addEventListener('pageshow', event => { if (event.persisted) { stopped = false; etag = null; poll(); } });
  poll();
})();
