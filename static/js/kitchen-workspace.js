(() => {
  const workspace = document.querySelector("[data-kitchen-workspace]");
  if (!workspace) return;

  const tabs = [...workspace.querySelectorAll("[data-kitchen-tab]")];
  const panels = [...workspace.querySelectorAll("[data-kitchen-panel]")];
  const feedback = workspace.querySelector("[data-kitchen-feedback]");
  const emptyMessages = {
    pending: "Không có món chờ.",
    cooking: "Chưa có món đang làm.",
    ready: "Chưa có món hoàn thành.",
  };

  const selectTab = (name) => {
    tabs.forEach((tab) => {
      const active = tab.dataset.kitchenTab === name;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
    });
    panels.forEach((panel) => panel.classList.toggle("active", panel.dataset.kitchenPanel === name));
  };

  const showFeedback = (message, tone = "danger") => {
    if (!feedback) return;
    feedback.textContent = message;
    feedback.className = `workspace-feedback alert alert-${tone}`;
    feedback.hidden = false;
    window.setTimeout(() => { feedback.hidden = true; }, 4000);
  };

  const refreshClock = (ticket) => {
    const anchor = Date.parse(ticket.dataset.slaAnchor || "");
    const threshold = Number(ticket.dataset.slaThreshold || 1);
    if (!Number.isFinite(anchor)) return;
    const elapsed = Math.max(0, Math.floor((Date.now() - anchor) / 60000));
    const warningAt = Math.max(1, Math.floor(threshold * 0.7));
    const level = elapsed >= threshold ? "overdue" : elapsed >= warningAt ? "warning" : "normal";
    ticket.classList.remove("is-sla-normal", "is-sla-warning", "is-sla-overdue");
    ticket.classList.add(`is-sla-${level}`);
    const clock = ticket.querySelector("[data-kitchen-elapsed]");
    if (clock) clock.textContent = `${ticket.dataset.slaPrefix} ${elapsed} phút${level === "overdue" ? " · Quá SLA" : ""}`;
  };

  const refreshClocks = () => workspace.querySelectorAll("[data-kitchen-ticket]").forEach(refreshClock);

  const updateCounts = (counts) => {
    Object.entries({pending: "PENDING", cooking: "COOKING", ready: "READY"}).forEach(([name, status]) => {
      const total = counts[status] ?? 0;
      workspace.querySelector(`[data-kitchen-panel="${name}"] > h2 strong`)?.replaceChildren(String(total));
      workspace.querySelector(`[data-kitchen-tab="${name}"] strong`)?.replaceChildren(String(total));
    });
  };

  const syncEmptyStates = () => {
    panels.forEach((panel) => {
      const name = panel.dataset.kitchenPanel;
      const hasTickets = Boolean(panel.querySelector("[data-kitchen-ticket]"));
      panel.querySelectorAll(":scope > .empty-state").forEach((node) => node.remove());
      if (!hasTickets) {
        const empty = document.createElement("p");
        empty.className = "empty-state";
        empty.textContent = emptyMessages[name];
        panel.append(empty);
      }
    });
  };

  tabs.forEach((tab) => tab.addEventListener("click", () => selectTab(tab.dataset.kitchenTab)));
  if (window.location.hash === "#pending") selectTab("pending");

  document.addEventListener("workspace:state-change", () => window.location.reload());

  workspace.addEventListener("submit", async (event) => {
    const form = event.target.closest("[data-kitchen-transition]");
    if (!form) return;
    event.preventDefault();
    if (form.dataset.loading === "true") return;
    form.dataset.loading = "true";
    document.dispatchEvent(new CustomEvent("workspace:busy", {detail: true}));
    const button = form.querySelector("button");
    if (button) {
      button.disabled = true;
      button.dataset.label = button.textContent;
      button.textContent = "Đang cập nhật…";
    }

    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: {"X-Requested-With": "XMLHttpRequest"},
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Không thể cập nhật món lúc này.");

      const ticket = form.closest("[data-kitchen-ticket]");
      const panelName = payload.status.toLowerCase();
      const targetPanel = workspace.querySelector(`[data-kitchen-panel="${panelName}"]`);
      ticket.dataset.status = payload.status;
      ticket.dataset.slaAnchor = payload.sla.anchor;
      ticket.dataset.slaThreshold = payload.sla.threshold;
      ticket.dataset.slaPrefix = payload.sla.prefix;

      if (payload.next_target) {
        form.action = payload.next_url;
        form.dataset.loading = "false";
        if (button) {
          button.disabled = false;
          button.textContent = payload.next_label;
        }
      } else {
        const badge = document.createElement("span");
        badge.className = "badge text-bg-success kitchen-ready-badge";
        badge.textContent = "Chờ phục vụ nhận món";
        form.replaceWith(badge);
      }

      targetPanel?.append(ticket);
      refreshClock(ticket);
      updateCounts(payload.counts);
      syncEmptyStates();
      document.dispatchEvent(new CustomEvent("workspace:mutation"));
      showFeedback("Đã cập nhật trạng thái món.", "success");
    } catch (error) {
      form.dataset.loading = "false";
      if (button) {
        button.disabled = false;
        button.textContent = button.dataset.label || "Thử lại";
      }
      showFeedback(error.message);
    } finally {
      document.dispatchEvent(new CustomEvent("workspace:busy", {detail: false}));
    }
  });

  refreshClocks();
  window.setInterval(refreshClocks, 30000);
})();
