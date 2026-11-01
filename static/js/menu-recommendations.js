(() => {
  const states = new WeakMap();
  const money = new Intl.NumberFormat("vi-VN");

  const addButton = (widget, id) => {
    const mode = widget.dataset.recommendationMode;
    if (mode === "qr") {
      const card = [...document.querySelectorAll("[data-qr-dish]")].find(node => node.dataset.id === String(id));
      return card?.querySelector("[data-qr-add]");
    }
    const forms = mode === "pos" ? document.querySelectorAll("[data-quick-add]") : document.querySelectorAll("[data-inline-add]");
    const form = [...forms].find(node => (node.dataset.dish || node.querySelector('[name="dish_id"]')?.value) === String(id));
    return form?.querySelector('button[type="submit"]');
  };

  const presentation = (widget, available, text = "") => {
    if (widget.dataset.recommendationDisplay !== "dialog") { widget.hidden = !available; return; }
    widget.hidden = false;
    const count = widget.querySelector("[data-recommendation-items]").children.length;
    document.querySelectorAll("[data-recommendation-toggle]").forEach(button => {
      if (button.dataset.recommendationTarget !== widget.id) return;
      button.disabled = !available;
      const badge = button.querySelector("[data-recommendation-count]");
      badge.textContent = String(count); badge.hidden = !count;
      button.setAttribute("aria-label", "Gợi ý ăn kèm: " + count + " món");
    });
    const status = widget.querySelector("[data-recommendation-status]");
    status.textContent = text; status.hidden = available;
  };

  const update = (widget, ids, frozen = false) => {
    let state = states.get(widget);
    if (!state) { state = {signature: null, controller: null, timer: null}; states.set(widget, state); }
    state.frozen = frozen;
    widget.querySelectorAll("button").forEach(button => { button.disabled = frozen; });
    const selected = [...new Set(ids.map(String))].sort();
    const signature = selected.join(",");
    if (signature === state.signature) return;
    state.signature = signature;
    clearTimeout(state.timer);
    state.controller?.abort();
    if (widget.dataset.recommendationDisplay === "dialog") widget.querySelector("[data-recommendation-items]").replaceChildren();
    presentation(widget, false, selected.length ? "Đang tìm gợi ý phù hợp…" : "Chọn món để xem gợi ý ăn kèm.");
    if (!selected.length) return;
    state.timer = setTimeout(async () => {
      if (!widget.isConnected) return;
      const controller = new AbortController();
      state.controller = controller;
      const timeout = setTimeout(() => controller.abort(), 6000);
      try {
        const url = new URL(widget.dataset.recommendationUrl, location.origin);
        selected.forEach(id => url.searchParams.append("dish", id));
        const response = await fetch(url, {signal: controller.signal, cache: "no-store", credentials: "same-origin", headers: {Accept: "application/json"}});
        if (!response.ok) throw new Error("Recommendations unavailable");
        const payload = await response.json();
        if (state.controller !== controller || state.signature !== signature || !widget.isConnected) return;
        const list = widget.querySelector("[data-recommendation-items]");
        list.replaceChildren();
        for (const item of (Array.isArray(payload.items) ? payload.items : []).slice(0, 3)) {
          if (!addButton(widget, item.id) || selected.includes(String(item.id))) continue;
          const card = document.createElement("article");
          card.className = "menu-recommendation-card";
          const name = document.createElement("strong"); name.textContent = item.name;
          const price = document.createElement("small"); price.textContent = money.format(Number(item.price)) + "đ";
          const button = document.createElement("button"); button.type = "button"; button.textContent = "＋ Thêm món";
          button.setAttribute("aria-label", "Thêm " + item.name);
          button.disabled = state.frozen;
          button.addEventListener("click", () => {
            const target = addButton(widget, item.id);
            if (target && !target.disabled && !state.frozen) {
              const panel = widget.querySelector("[data-recommendation-dialog]");
              if (panel?.open) panel.close();
              target.click();
            }
          });
          card.append(name, price, button); list.appendChild(card);
        }
        presentation(widget, list.children.length > 0, "Chưa có gợi ý phù hợp với các món đã chọn.");
      } catch (error) {
        if (state.controller === controller && state.signature === signature) { presentation(widget, false, "Chưa tải được gợi ý. Bạn vẫn có thể chọn món bình thường."); state.signature = null; }
      } finally { clearTimeout(timeout); }
    }, 160);
  };

  const refreshStaff = () => {
    document.querySelectorAll("[data-menu-recommendations]").forEach(widget => {
      const mode = widget.dataset.recommendationMode;
      if (mode === "qr") return;
      const root = mode === "pos" ? document.querySelector(".sales-order-panel") : widget;
      const ids = [...(root?.querySelectorAll("[data-recommendation-seed]") || [])].map(node => node.dataset.recommendationSeed);
      if (mode === "staff") {
        document.querySelectorAll("[data-inline-add]").forEach(form => {
          if (Number(form.querySelector("[data-dish-count]")?.textContent) > 0) ids.push(form.dataset.dish);
        });
      }
      if (mode === "pos" && !["OPEN", "IN_PROGRESS"].includes(root?.dataset.recommendationsOrderStatus)) ids.length = 0;
      update(widget, ids);
    });
  };

  document.addEventListener("click", event => {
    const toggle = event.target.closest("[data-recommendation-toggle]");
    if (toggle && !toggle.disabled) {
      const widget = document.getElementById(toggle.dataset.recommendationTarget);
      const panel = widget?.querySelector("[data-recommendation-dialog]");
      if (panel && !panel.open) panel.showModal();
    }
    const close = event.target.closest("[data-recommendation-close]");
    if (close) close.closest("dialog").close();
    if (event.target.matches("[data-recommendation-dialog]")) {
      const r = event.target.getBoundingClientRect();
      if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) event.target.close();
    }
  });

  document.addEventListener("qr:cart-change", event => {
    document.querySelectorAll('[data-menu-recommendations][data-recommendation-mode="qr"]').forEach(widget => {
      update(widget, event.detail.ids, event.detail.frozen);
    });
  });
  ["DOMContentLoaded", "workspace:mutation", "workspace:content-replaced", "mobile:page-ready"].forEach(event => {
    document.addEventListener(event, refreshStaff);
  });
})();
