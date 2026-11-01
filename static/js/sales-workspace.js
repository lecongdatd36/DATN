document.addEventListener("DOMContentLoaded", () => {
  const workspace = document.querySelector(".sales-workspace");
  if (!workspace) return;

  let search;
  let categoryButtons = [];
  let cards = [];
  const searchNames = new WeakMap();
  let empty;
  const feedback = workspace.querySelector("[data-sales-feedback]");
  const phoneQuery = window.matchMedia("(max-width: 767.98px)");
  if (phoneQuery.matches && workspace.dataset.mobileUrl && new URLSearchParams(location.search).get("desktop") !== "1") {
    const destination = new URL(workspace.dataset.mobileUrl, location.origin);
    const current = new URLSearchParams(location.search);
    for (const key of ["order", "table"]) if (current.has(key)) destination.searchParams.set(key, current.get(key));
    if (current.has("open_table")) {
      destination.searchParams.set("table", current.get("open_table"));destination.searchParams.set("page", "open");
    } else if (current.has("order") || current.has("table")) {
      destination.searchParams.set("page", location.hash === "#sales-menu" ? "menu" : "order");
    }
    location.replace(destination.href);return;
  }
  let category = "all";
  let searchTimer;

  const showFeedback = (message, tone = "danger") => {
    if (!feedback) return;
    feedback.textContent = message;
    feedback.className = `workspace-feedback alert alert-${tone}`;
    feedback.hidden = false;
    window.setTimeout(() => { feedback.hidden = true; }, 4000);
  };

  const showMobileOrder = (scrollToCheckout = false) => {
    workspace.classList.remove("is-mobile-menu-open");
    const title = workspace.querySelector("[data-mobile-pos-title]");
    if (title) title.textContent = "Order";
    if (scrollToCheckout) {
      workspace.classList.add("is-mobile-checkout-open");
      window.setTimeout(() => workspace.querySelector(".checkout-card")?.scrollIntoView({behavior: "smooth", block: "start"}), 180);
    }
  };
  const showMobileMenu = () => {
    workspace.classList.add("is-mobile-menu-open");
    const title = workspace.querySelector("[data-mobile-pos-title]");
    if (title) title.textContent = "Thêm món";
    window.scrollTo({top: 0, behavior: "smooth"});
  };

  const normalize = (value) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[đĐ]/g, "d").toLowerCase().trim();
  const filterDishes = () => {
    const query = normalize(search?.value || "");
    let visible = 0;
    cards.forEach((card) => {
      const categoryMatches = category === "all" || card.dataset.category === category;
      const textMatches = !query || searchNames.get(card).includes(query);
      const hidden = !(categoryMatches && textMatches);
      if (card.hidden !== hidden) card.hidden = hidden;
      if (!hidden) visible += 1;
    });
    if (empty) empty.hidden = visible !== 0;
  };

  const bindMenuControls = () => {
    search = workspace.querySelector("[data-dish-search]");
    categoryButtons = [...workspace.querySelectorAll("[data-category-filter] button")];
    cards = [...workspace.querySelectorAll("[data-dish-grid] .dish-card")];
    cards.forEach((card) => searchNames.set(card, normalize(card.dataset.dishName || "")));
    empty = workspace.querySelector("[data-dish-empty]");
    category = "all";
    search?.addEventListener("input", () => {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(filterDishes, 280);
    });
    categoryButtons.forEach((button) => button.addEventListener("click", () => {
      category = button.dataset.category || "all";
      categoryButtons.forEach((item) => item.classList.toggle("active", item === button));
      filterDishes();
    }));
  };
  bindMenuControls();

  workspace.addEventListener("click", (event) => {
    const orderToggle = event.target.closest("[data-mobile-order-toggle]");
    if (orderToggle && phoneQuery.matches) {
      showMobileOrder(orderToggle.hasAttribute("data-scroll-checkout"));
      return;
    }
    if (event.target.closest("[data-mobile-show-menu]") && phoneQuery.matches) {
      showMobileMenu();
      return;
    }
    if (event.target.closest("[data-mobile-order-close]")) {
      showMobileOrder();
      return;
    }

    const stepButton = event.target.closest("[data-quantity-step]");
    if (stepButton) {
      const input = stepButton.closest(".quantity-stepper")?.querySelector("input[type='number']");
      if (!input) return;
      const step = Number(stepButton.dataset.quantityStep || 0);
      const min = Number(input.min || 1);
      const max = Number(input.max || 100);
      input.value = String(Math.min(max, Math.max(min, Number(input.value || min) + step)));
      input.closest("form")?.requestSubmit();
      return;
    }

    const noteToggle = event.target.closest("[data-order-note-toggle]");
    if (noteToggle) {
      const form = noteToggle.closest("[data-order-item-form]");
      form?.classList.toggle("is-note-editing");
      if (form?.classList.contains("is-note-editing")) form.querySelector(".order-note-input")?.focus();
      return;
    }

    if (event.target.closest("[data-mobile-scroll-checkout]")) {
      workspace.classList.add("is-mobile-checkout-open");
      workspace.querySelector(".checkout-card")?.scrollIntoView({behavior: "smooth", block: "start"});
      return;
    }

    const orderStepButton = event.target.closest("[data-order-qty-step]");
    if (orderStepButton) {
      const input = orderStepButton.closest(".order-qty-stepper")?.querySelector("input[type='number']");
      if (!input) return;
      const step = Number(orderStepButton.dataset.orderQtyStep || 0);
      const min = Number(input.min || 1);
      const max = Number(input.max || 100);
      input.value = String(Math.min(max, Math.max(min, Number(input.value || min) + step)));
      return;
    }

    const guestStepButton = event.target.closest("[data-guest-step]");
    if (guestStepButton) {
      const form = guestStepButton.closest("form");
      const input = form?.querySelector("input[name='guest_count']");
      if (!input) return;
      const step = Number(guestStepButton.dataset.guestStep || 0);
      const min = Number(input.min || 1);
      const max = Number(input.max || 100);
      input.value = String(Math.min(max, Math.max(min, Number(input.value || min) + step)));
      form.querySelector("[data-guest-preview]").textContent = input.value;
      return;
    }

    const mobileGo = event.target.closest("[data-mobile-go]");
    if (mobileGo && window.bootstrap) {
      const selector = mobileGo.dataset.mobileGo;
      if (phoneQuery.matches && selector === "#sales-menu") {
        showMobileMenu();
        return;
      }
      if (phoneQuery.matches && selector === "#sales-order") {
        showMobileOrder(mobileGo.hasAttribute("data-scroll-checkout"));
        return;
      }
      const trigger = workspace.querySelector(`[data-bs-target="${selector}"]`);
      if (trigger) window.bootstrap.Tab.getOrCreateInstance(trigger).show();
      if (mobileGo.hasAttribute("data-scroll-checkout")) {
        window.setTimeout(() => workspace.querySelector(".checkout-card")?.scrollIntoView({behavior: "smooth", block: "start"}), 120);
      }
    }
  });

  const lineMarkup = (line) => {
    const copy = line.cloneNode(true);
    copy.querySelectorAll(".is-note-editing").forEach(node => node.classList.remove("is-note-editing"));
    copy.querySelectorAll("input[name='csrfmiddlewaretoken'], input[name='expected_revision']")
      .forEach((input) => input.removeAttribute("value"));
    return copy.outerHTML;
  };

  const syncOrderFromResponse = (html, notifyMutation = true) => {
    const scrollPosition = {x: window.scrollX, y: window.scrollY};
    const panelPositions = new Map([".sales-order-panel", ".mobile-order-dock", ".mobile-pos-appbar"].map(selector => {
      const panel = workspace.querySelector(selector);
      return [selector, {top: panel?.scrollTop || 0, left: panel?.scrollLeft || 0}];
    }));
    const menu = workspace.querySelector("#sales-menu");
    const menuBounds = menu?.getBoundingClientRect();
    const menuAnchor = menu && [...menu.querySelectorAll("[data-quick-add]:not([hidden])")].find(card => {
      const r = card.getBoundingClientRect();
      return r.top >= menuBounds.top + 50 && r.top < menuBounds.bottom;
    });
    const anchorTop = menuAnchor?.getBoundingClientRect().top;
    const active = document.activeElement;
    const activeLine = active?.closest("[data-order-item-id]")?.dataset.orderItemId;
    const focus = active?.closest(".sales-order-panel") && active.matches("input, textarea, select")
      ? {element: active, line: activeLine, name: active.name, type: active.type, start: active.selectionStart, end: active.selectionEnd} : null;
    const responseDocument = new DOMParser().parseFromString(html, "text/html");
    const incomingRevision = Number(responseDocument.querySelector("[data-order-revision]")?.value);
    const currentRevision = Number(workspace.querySelector("[data-order-revision]")?.value);
    if (
      Number.isFinite(incomingRevision)
      && Number.isFinite(currentRevision)
      && incomingRevision < currentRevision
    ) return;
    // Reuse unchanged rows, including their decoded images, instead of
    // rebuilding every item when just one quantity or status changes.
    const oldLines = new Map([...workspace.querySelectorAll("[data-order-item-id]")]
      .map((line) => [line.dataset.orderItemId, line]));
    responseDocument.querySelectorAll("[data-order-item-id]").forEach((line) => {
      const previous = oldLines.get(line.dataset.orderItemId);
      if (previous && lineMarkup(previous) === lineMarkup(line)) line.replaceWith(previous);
    });
    const checkout = workspace.querySelector("[data-checkout-form]");
    const nextCheckout = responseDocument.querySelector("[data-checkout-form]");
    if (checkout && nextCheckout) {
      // Typed payment details belong to this device, not to the refresh HTML.
      checkout.querySelectorAll("input:not([type='hidden']), select, textarea").forEach((field) => {
        const target = [...nextCheckout.elements].find((candidate) =>
          candidate.name === field.name && candidate.type === field.type
          && (!['radio', 'checkbox'].includes(field.type) || candidate.value === field.value));
        if (!target) return;
        if (['radio', 'checkbox'].includes(field.type)) target.checked = field.checked;
        else target.value = field.value;
      });
      const options = checkout.querySelector("[data-checkout-options]");
      const nextOptions = nextCheckout.querySelector("[data-checkout-options]");
      if (options && nextOptions) nextOptions.open = options.open;
    }
    [".sales-order-panel", ".mobile-order-dock", ".mobile-pos-appbar"].forEach((selector) => {
      const current = workspace.querySelector(selector);
      const replacement = responseDocument.querySelector(selector);
      if (current && replacement) {
        const {top, left} = panelPositions.get(selector);
        for (const name of ["active", "show"]) replacement.classList.toggle(name, current.classList.contains(name));
        current.replaceWith(replacement);
        replacement.scrollTop = top; replacement.scrollLeft = left;
      }
    });
    const revision = responseDocument.querySelector("[data-order-revision]")?.value
      || responseDocument.querySelector("input[name='expected_revision']")?.value;
    if (revision) workspace.querySelectorAll("input[name='expected_revision']").forEach((input) => { input.value = revision; });
    const dock = workspace.querySelector(".mobile-order-dock");
    if (dock) {
      dock.classList.remove("is-updated");
      window.requestAnimationFrame(() => dock.classList.add("is-updated"));
      window.setTimeout(() => dock.classList.remove("is-updated"), 500);
    }
    bindCheckoutControls();
    bindGuestPreviews();
    const orderOpen = ["OPEN", "IN_PROGRESS"].includes(workspace.querySelector(".sales-order-panel")?.dataset.recommendationsOrderStatus);
    workspace.querySelectorAll("[data-quick-add] button[type='submit']").forEach(button => { button.disabled = !orderOpen || button.closest("form").dataset.loading === "true"; });
    if (focus) {
      const line = [...workspace.querySelectorAll("[data-order-item-id]")].find(node => node.dataset.orderItemId === focus.line);
      const target = focus.element.isConnected ? focus.element : [...(line || workspace.querySelector(".sales-order-panel")).querySelectorAll("input, textarea, select")].find(node => node.name === focus.name && node.type === focus.type);
      target?.focus({preventScroll: true});
      if (target && typeof focus.start === "number" && target.setSelectionRange) target.setSelectionRange(focus.start, focus.end);
    }
    if (notifyMutation) document.dispatchEvent(new CustomEvent("workspace:mutation"));
    window.scrollTo({left: scrollPosition.x, top: scrollPosition.y, behavior: "instant"});
    const restoreMenuAnchor = () => {
      if (menuAnchor?.isConnected) menu.scrollTop += menuAnchor.getBoundingClientRect().top - anchorTop;
    };
    restoreMenuAnchor();
    const settledScroll = menu?.scrollTop;
    window.requestAnimationFrame(() => {
      if (menu?.isConnected && Math.abs(menu.scrollTop - settledScroll) < 2) restoreMenuAnchor();
    });
  };

  const replaceWorkspaceElement = (responseDocument, selector) => {
    const current = workspace.querySelector(selector);
    const replacement = responseDocument.querySelector(selector);
    if (current && replacement) {
      current.replaceWith(replacement);
    } else if (replacement) {
      workspace.querySelector(".sales-grid")?.before(replacement);
    } else {
      current?.remove();
    }
  };

  const syncWorkspaceFromResponse = (html) => {
    const responseDocument = new DOMParser().parseFromString(html, "text/html");
    const incomingWorkspace = responseDocument.querySelector(".sales-workspace");
    if (!incomingWorkspace) throw new Error("Không thể nhận dữ liệu bàn vừa mở.");

    workspace.classList.toggle("has-selected-order", incomingWorkspace.classList.contains("has-selected-order"));
    workspace.dataset.selectedOrderId = incomingWorkspace.dataset.selectedOrderId || "";
    [".sales-mobile-tabs", "#sales-tables", "#sales-menu", ".sales-order-panel"].forEach((selector) => {
      const current = workspace.querySelector(selector);
      const replacement = responseDocument.querySelector(selector);
      if (current && replacement) current.replaceWith(replacement);
    });
    replaceWorkspaceElement(responseDocument, ".mobile-pos-appbar");
    replaceWorkspaceElement(responseDocument, ".mobile-order-dock");
    bindMenuControls();
    bindCheckoutControls();
    bindGuestPreviews();
    document.dispatchEvent(new CustomEvent("workspace:content-replaced", {detail: {scope: workspace}}));
    document.dispatchEvent(new CustomEvent("workspace:mutation"));
  };

  const syncTablesFromResponse = (html) => {
    const responseDocument = new DOMParser().parseFromString(html, "text/html");
    const current = workspace.querySelector("#sales-tables");
    const replacement = responseDocument.querySelector("#sales-tables");
    if (!current || !replacement) throw new Error("Không thể đồng bộ danh sách bàn.");
    current.replaceWith(replacement);
    document.dispatchEvent(new CustomEvent("workspace:content-replaced", {detail: {scope: workspace}}));
  };

  const isRevisionConflict = (message) => /đơn đã thay đổi|revision|stale/i.test(message || "");
  const refreshOrderRevision = async () => {
    const response = await fetch(window.location.href, {
      headers: {"X-Requested-With": "XMLHttpRequest", "X-Order-Fragment": "1"},
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error(`Không thể đồng bộ order (HTTP ${response.status}).`);
    syncOrderFromResponse(await response.text());
    return workspace.querySelector("[data-order-revision]")?.value;
  };
  const submitOrderAction = async (form) => {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: {"X-Requested-With": "XMLHttpRequest", "X-Order-Fragment": "1"},
      });
      const contentType = response.headers.get("content-type") || "";
      if (response.ok) return response.text();
      const payload = contentType.includes("application/json") ? await response.json() : null;
      const message = payload?.error || "Không thể cập nhật món lúc này.";
      if (!isRevisionConflict(message) || attempt > 0) throw new Error(message);
      const revision = await refreshOrderRevision();
      if (!revision) throw new Error(message);
      form.querySelectorAll("input[name='expected_revision']").forEach((input) => { input.value = revision; });
    }
    throw new Error("Không thể cập nhật món lúc này.");
  };

  let refreshInProgress = false;
  let refreshPending = false;
  let workspaceBusy = false;
  let workspaceBusyCount = 0;
  let tablesRefreshInProgress = false;
  const isEditingOrder = () => workspace.querySelector(
    ".sales-order-panel input:focus, .sales-order-panel textarea:focus, .sales-order-panel select:focus, .is-note-editing"
  );
  const refreshSelectedOrder = async () => {
    if (workspaceBusy || isEditingOrder() || document.hidden) {
      refreshPending = true;
      return;
    }
    if (refreshInProgress) {
      refreshPending = true;
      return;
    }
    if (!workspace.classList.contains("has-selected-order")) return;
    refreshPending = false;
    refreshInProgress = true;
    try {
      const response = await fetch(window.location.href, {
        headers: {"X-Requested-With": "XMLHttpRequest", "X-Order-Fragment": "1"},
        cache: "no-store",
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error(`Không thể đồng bộ order (HTTP ${response.status}).`);
      const html = await response.text();
      if (workspaceBusy || isEditingOrder() || document.hidden) refreshPending = true;
      else syncOrderFromResponse(html, false);
    } catch (error) {
      showFeedback(error.message);
    } finally {
      refreshInProgress = false;
      if (refreshPending && !workspaceBusy && !isEditingOrder() && !document.hidden) {
        refreshPending = false;
        refreshSelectedOrder();
      }
    }
  };

  workspace.addEventListener("focusout", () => {
    window.setTimeout(() => {
      if (refreshPending && !isEditingOrder()) refreshSelectedOrder();
    }, 0);
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && refreshPending) refreshSelectedOrder();
  });

  const refreshTables = async () => {
    if (tablesRefreshInProgress || workspaceBusy) return;
    tablesRefreshInProgress = true;
    try {
      const response = await fetch(window.location.href, {
        headers: {"X-Requested-With": "XMLHttpRequest", "X-POS-Tables-Refresh": "1"},
        cache: "no-store",
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error(`Không thể đồng bộ bàn (HTTP ${response.status}).`);
      syncTablesFromResponse(await response.text());
    } catch (error) {
      showFeedback(error.message);
    } finally {
      tablesRefreshInProgress = false;
    }
  };

  let lastSalesState = workspace.__qlnhLiveState || null;
  let workspaceRefreshTimer = null;

  const refreshTablesAfterStateChange = (hasNotification) => {
    const isTablesTab = workspace.querySelector("#sales-tables.active") || !workspace.classList.contains("has-selected-order");
    if (!isTablesTab || workspaceBusy || workspace.querySelector("input:focus")) return;
    window.clearTimeout(workspaceRefreshTimer);
    // Keep the sound audible, then replace only the table panel.  Reloading
    // the whole page here interrupted active POS work and felt sluggish.
    workspaceRefreshTimer = window.setTimeout(
      refreshTables,
      hasNotification ? 1800 : 450,
    );
  };

  const handleSalesStateChange = (event) => {
    const data = event?.detail;
    let hasNotification = false;
    if (data && lastSalesState) {
      const newPay = Number(data.payment_requests?.count || 0);
      const prevPay = Number(lastSalesState.payment_requests?.count || 0);
      if (newPay > prevPay) {
        hasNotification = true;
        window.QLNHAudio?.play("payment");
        window.QLNHAudio?.toast("Có yêu cầu thanh toán mới!", "💰", "success");
      }

      const newService = Number(data.qr_service_requests?.count || 0);
      const prevService = Number(lastSalesState.qr_service_requests?.count || 0);
      if (newService > prevService) {
        hasNotification = true;
        window.QLNHAudio?.play("service");
        window.QLNHAudio?.toast("Khách quét QR gọi phục vụ!", "🙋", "info");
      }

      const newCheckIn = Number(data.qr_check_ins?.count || 0);
      const prevCheckIn = Number(lastSalesState.qr_check_ins?.count || 0);
      if (newCheckIn > prevCheckIn) {
        hasNotification = true;
        window.QLNHAudio?.play("service");
        window.QLNHAudio?.toast("Khách quét QR yêu cầu nhận bàn!", "📱", "info");
      }

      const newQROrder = Number(data.qr_orders?.count || 0);
      const prevQROrder = Number(lastSalesState.qr_orders?.count || 0);
      if (newQROrder > prevQROrder) {
        hasNotification = true;
        window.QLNHAudio?.play("order");
        window.QLNHAudio?.toast("Có yêu cầu gọi món QR mới!", "🛒", "primary");
      }
    }
    if (data) lastSalesState = data;
    refreshSelectedOrder();
    refreshTablesAfterStateChange(hasNotification);
  };

  document.addEventListener("workspace:state-ready", (event) => {
    if (event.detail) lastSalesState = event.detail;
  });
  document.addEventListener("workspace:state-change", handleSalesStateChange);
  document.addEventListener("workspace:busy", (event) => {
    workspaceBusyCount = event.detail ? workspaceBusyCount + 1 : Math.max(0, workspaceBusyCount - 1);
    workspaceBusy = workspaceBusyCount > 0;
    if (!workspaceBusy && refreshPending) {
      refreshPending = false;
      refreshSelectedOrder();
    }
  });

  workspace.addEventListener("submit", async (event) => {
    const form = event.target.closest(".open-table-modal");
    if (!form) return;
    event.preventDefault();
    if (form.dataset.loading === "true") return;
    form.dataset.loading = "true";
    form.classList.add("is-updating");
    form.querySelectorAll("button").forEach((button) => { button.disabled = true; });
    document.dispatchEvent(new CustomEvent("workspace:busy", {detail: true}));
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: {"X-Requested-With": "XMLHttpRequest", "X-Open-Workspace": "1"},
      });
      if (!response.ok) {
        const contentType = response.headers.get("content-type") || "";
        const payload = contentType.includes("application/json") ? await response.json() : null;
        throw new Error(payload?.error || "Không thể mở bàn lúc này.");
      }
      const modal = form.closest(".modal");
      window.bootstrap?.Modal.getInstance(modal)?.hide();
      document.querySelectorAll(".modal-backdrop").forEach((backdrop) => backdrop.remove());
      document.body.classList.remove("modal-open");
      document.body.style.removeProperty("padding-right");
      syncWorkspaceFromResponse(await response.text());
      const orderId = workspace.dataset.selectedOrderId;
      if (!orderId) throw new Error("Không tìm thấy order của bàn vừa mở.");
      const target = new URL(window.location.href);
      target.searchParams.delete("open_table");
      target.searchParams.set("order", orderId);
      target.hash = "sales-menu";
      window.history.replaceState({}, "", `${target.pathname}${target.search}${target.hash}`);
      if (phoneQuery.matches) {
        showMobileMenu();
      } else {
        const menuTab = workspace.querySelector('[data-bs-target="#sales-menu"]');
        if (menuTab && window.bootstrap) window.bootstrap.Tab.getOrCreateInstance(menuTab).show();
      }
    } catch (error) {
      showFeedback(error.message);
    } finally {
      form.dataset.loading = "false";
      form.classList.remove("is-updating");
      form.querySelectorAll("button").forEach((button) => { button.disabled = false; });
      document.dispatchEvent(new CustomEvent("workspace:busy", {detail: false}));
    }
  });

  workspace.addEventListener("submit", async (event) => {
    // Sending draft items to the kitchen follows the same fragment update as
    // editing an item. This avoids a full POS navigation after every send.
    const form = event.target.closest("[data-order-item-form], form[action$='/action/send/'], form[action$='/action/request-payment/']");
    if (!form) return;
    event.preventDefault();
    if (form.dataset.loading === "true") return;
    form.dataset.loading = "true";
    form.classList.add("is-updating");
    form.querySelectorAll("button").forEach((button) => { button.disabled = true; });
    document.dispatchEvent(new CustomEvent("workspace:busy", {detail: true}));
    try {
      syncOrderFromResponse(await submitOrderAction(form));
    } catch (error) {
      form.classList.add("is-add-error");
      showFeedback(error.message);
      window.setTimeout(() => form.classList.remove("is-add-error"), 900);
    } finally {
      form.dataset.loading = "false";
      form.classList.remove("is-updating");
      form.querySelectorAll("button").forEach((button) => { button.disabled = false; });
      document.dispatchEvent(new CustomEvent("workspace:busy", {detail: false}));
    }
  });

  workspace.addEventListener("submit", async (event) => {
    const form = event.target.closest("[data-quick-add]");
    if (!form) return;
    event.preventDefault();
    if (form.dataset.loading === "true") return;
    const button = form.querySelector(".dish-quick-add");
    form.dataset.loading = "true";
    form.classList.add("is-adding");
    if (button) button.disabled = true;
    document.dispatchEvent(new CustomEvent("workspace:busy", {detail: true}));
    try {
      syncOrderFromResponse(await submitOrderAction(form));
      form.classList.add("is-added");
      const note = form.querySelector("input[name='note']");
      if (note) note.value = "";
      const details = form.querySelector("details");
      if (details) details.open = false;
      window.setTimeout(() => form.classList.remove("is-added"), 450);
    } catch (error) {
      form.classList.add("is-add-error");
      if (button) button.setAttribute("aria-label", error.message);
      showFeedback(error.message);
      window.setTimeout(() => form.classList.remove("is-add-error"), 900);
    } finally {
      form.dataset.loading = "false";
      form.classList.remove("is-adding");
      if (button) button.disabled = !["OPEN", "IN_PROGRESS"].includes(workspace.querySelector(".sales-order-panel")?.dataset.recommendationsOrderStatus);
      document.dispatchEvent(new CustomEvent("workspace:busy", {detail: false}));
    }
  });

  const bindCheckoutControls = () => workspace.querySelectorAll("[data-checkout-form]").forEach((form) => {
    if (form.dataset.checkoutBound === "true") return;
    form.dataset.checkoutBound = "true";
    const options = form.querySelector("[data-checkout-options]");
    const transactionField = form.querySelector("[data-transaction-field]");
    const syncPaymentFields = () => {
      const method = form.querySelector("input[name='payment_method']:checked")?.value;
      const needsReference = method === "BANK_TRANSFER";
      if (transactionField) transactionField.hidden = !needsReference;
      if (needsReference && options) options.open = true;
    };
    form.querySelectorAll("input[name='payment_method']").forEach((input) => input.addEventListener("change", syncPaymentFields));
    syncPaymentFields();
  });

  const bindGuestPreviews = () => workspace.querySelectorAll("input[name='guest_count']").forEach((input) => {
    if (input.dataset.guestPreviewBound === "true") return;
    input.dataset.guestPreviewBound = "true";
    input.addEventListener("input", () => {
      const preview = input.closest("form")?.querySelector("[data-guest-preview]");
      if (preview) preview.textContent = input.value || "1";
    });
  });

  bindCheckoutControls();
  bindGuestPreviews();

  if (phoneQuery.matches && workspace.classList.contains("has-selected-order")) {
    if (window.location.hash === "#sales-menu") showMobileMenu();
    else showMobileOrder(window.location.hash === "#checkout");
  } else if (window.location.hash && window.bootstrap) {
    const trigger = workspace.querySelector(`[data-bs-target="${window.location.hash}"]`);
    if (trigger) window.bootstrap.Tab.getOrCreateInstance(trigger).show();
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && workspace.classList.contains("is-mobile-menu-open")) showMobileOrder();
  });
  const handlePhoneChange = () => { if (!phoneQuery.matches) showMobileOrder(); };
  if (phoneQuery.addEventListener) phoneQuery.addEventListener("change", handlePhoneChange);
  else phoneQuery.addListener(handlePhoneChange);

  const openTable = new URLSearchParams(window.location.search).get("open_table");
  if (openTable && window.bootstrap) {
    const modal = document.getElementById(`open-table-${openTable}`);
    if (modal) window.bootstrap.Modal.getOrCreateInstance(modal).show();
  }
});
