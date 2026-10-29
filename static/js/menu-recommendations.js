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
    widget.hidden = true;
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
            if (target && !target.disabled && !state.frozen) target.click();
          });
          card.append(name, price, button); list.appendChild(card);
        }
        widget.hidden = !list.children.length;
      } catch (error) {
        if (state.controller === controller && state.signature === signature) { widget.hidden = true; state.signature = null; }
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

  document.addEventListener("qr:cart-change", event => {
    document.querySelectorAll('[data-menu-recommendations][data-recommendation-mode="qr"]').forEach(widget => {
      update(widget, event.detail.ids, event.detail.frozen);
    });
  });
  ["DOMContentLoaded", "workspace:mutation", "workspace:content-replaced", "mobile:page-ready"].forEach(event => {
    document.addEventListener(event, refreshStaff);
  });
})();
