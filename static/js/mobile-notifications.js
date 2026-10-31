/* Persistent notification controls: independent of the replaceable mobile page. */
(() => {
  "use strict";
  const panel = document.querySelector("[data-mobile-notification-panel]");
  if (!panel) return;
  const toast = document.querySelector("[data-mobile-notification-toast]");
  const message = document.querySelector("[data-mobile-notification-message]");
  const status = panel.querySelector("[data-mobile-notification-status]");
  let previous = null, toastTimer;
  const hideToast = () => { clearTimeout(toastTimer); toast.hidden = true; };
  document.addEventListener("click", event => {
    if (event.target.closest("[data-mobile-notification-open]")) {
      if (!panel.open) panel.showModal();
      hideToast();
    } else if (event.target.closest("[data-mobile-notification-close]")) panel.close();
    else if (event.target.closest("[data-mobile-notification-dismiss]")) hideToast();
    else if (event.target.closest("[data-notification-entry]") && panel.contains(event.target)) panel.close();
    else if (event.target === panel) {
      const r = panel.getBoundingClientRect();
      if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) panel.close();
    }
  });
  document.addEventListener("notifications:updated", event => {
    const entries = event.detail.entries;
    const next = new Map(entries.map(entry => [entry.key, entry.count]));
    const added = previous ? entries.filter(entry => previous.has(entry.key) && entry.count > previous.get(entry.key)) : [];
    previous = next;
    if (!added.length || document.hidden) return;
    const item = added.find(entry => entry.key === "payments") || added[0];
    message.textContent = added.length === 1 ? item.label + ": " + item.count + " đang chờ." : added.length + " nhóm công việc có cập nhật mới.";
    if (!panel.open) {
      toast.hidden = false;
      clearTimeout(toastTimer);
      toastTimer = setTimeout(hideToast, 6000);
    }
    window.QLNHAudio?.play(item.key === "payments" ? "payment" : item.key === "ready" ? "ready" : ["qr_orders", "kitchen"].includes(item.key) ? "order" : "service");
  });
  document.addEventListener("notifications:status", event => {
    const state = event.detail;
    status.textContent = state === "online" ? "Đã đồng bộ · Tự cập nhật mỗi 5 giây." : state === "expired" ? "Phiên làm việc đã hết hoặc quyền đã đổi. Vui lòng đăng nhập lại." : "Chưa kết nối được. Đang hiển thị lần cập nhật gần nhất và sẽ thử lại.";
    status.classList.toggle("is-offline", state !== "online");
    if (state === "expired") { previous = null; hideToast(); }
  });
})();
