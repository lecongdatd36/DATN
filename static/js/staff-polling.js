(() => {
  const root = document.querySelector("[data-live-workspace]");
  if (!root) return;
  let signature = null;
  const poll = async () => {
    try {
      const response = await fetch(root.dataset.stateUrl, {headers: {"X-Requested-With": "XMLHttpRequest"}, cache: "no-store"});
      if (!response.ok) return;
      const next = JSON.stringify(await response.json());
      if (signature !== null && signature !== next) window.location.reload();
      signature = next;
    } catch (_) {}
  };
  poll();
  window.setInterval(poll, 7000);
})();
