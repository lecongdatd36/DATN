document.addEventListener("DOMContentLoaded", () => {
  const workspace = document.querySelector(".sales-workspace");
  if (!workspace) return;

  let search;
  let categoryButtons = [];
  let cards = [];
  let empty;
  const feedback = workspace.querySelector("[data-sales-feedback]");
  const phoneQuery = window.matchMedia("(max-width: 767.98px)");
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
    window.setTimeout(() => search?.focus({preventScroll: true}), 180);
  };

  const normalize = (value) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
  const filterDishes = () => {
    const query = normalize(search?.value || "");
    let visible = 0;
    cards.forEach((card) => {
      const categoryMatches = category === "all" || card.dataset.category === category;
      const textMatches = !query || normalize(card.dataset.dishName || "").includes(query);
      card.hidden = !(categoryMatches && textMatches);
      if (!card.hidden) visible += 1;
    });
    if (empty) empty.hidden = visible !== 0;
  };

  const bindMenuControls = () => {
    search = workspace.querySelector("[data-dish-search]");
    categoryButtons = [...workspace.querySelectorAll("[data-category-filter] button")];
    cards = [...workspace.querySelectorAll("[data-dish-grid] .dish-card")];
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

  const syncOrderFromResponse = (html) => {
    const responseDocument = new DOMParser().parseFromString(html, "text/html");
    const incomingRevision = Number(responseDocument.querySelector("[data-order-revision]")?.value);
    const currentRevision = Number(workspace.querySelector("[data-order-revision]")?.value);
    if (
      Number.isFinite(incomingRevision)
      && Number.isFinite(currentRevision)
      && incomingRevision < currentRevision
    ) return;
    [".sales-order-panel", ".mobile-order-dock", ".mobile-pos-appbar"].forEach((selector) => {
      const current = workspace.querySelector(selector);
      const replacement = responseDocument.querySelector(selector);
      if (current && replacement) current.replaceWith(replacement);
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
    document.dispatchEvent(new CustomEvent("workspace:mutation"));
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
    document.dispatchEvent(new CustomEvent("workspace:mutation"));
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
  let tablesRefreshInProgress = false;
  const refreshSelectedOrder = async () => {
    if (workspaceBusy) {
      refreshPending = true;
      return;
    }
    if (refreshInProgress) {
      refreshPending = true;
      return;
    }
    if (!workspace.classList.contains("has-selected-order")) return;
    refreshInProgress = true;
    try {
      const response = await fetch(window.location.href, {
        headers: {"X-Requested-With": "XMLHttpRequest", "X-Order-Fragment": "1"},
        cache: "no-store",
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error(`Không thể đồng bộ order (HTTP ${response.status}).`);
      syncOrderFromResponse(await response.text());
    } catch (error) {
      showFeedback(error.message);
    } finally {
      refreshInProgress = false;
      if (refreshPending) {
        refreshPending = false;
        refreshSelectedOrder();
      }
    }
  };

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
    workspaceBusy = event.detail ? true : false;
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
    const form = event.target.closest("[data-order-item-form], form[action$='/action/send/']");
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
      if (button) button.disabled = false;
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
