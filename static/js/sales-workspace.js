document.addEventListener("DOMContentLoaded", () => {
  const workspace = document.querySelector(".sales-workspace");
  if (!workspace) return;

  const search = workspace.querySelector("[data-dish-search]");
  const categoryButtons = [...workspace.querySelectorAll("[data-category-filter] button")];
  const cards = [...workspace.querySelectorAll("[data-dish-grid] .dish-card")];
  const empty = workspace.querySelector("[data-dish-empty]");
  const feedback = workspace.querySelector("[data-sales-feedback]");
  const phoneQuery = window.matchMedia("(max-width: 767.98px)");
  let category = "all";

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

  let searchTimer;
  search?.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(filterDishes, 280);
  });
  categoryButtons.forEach((button) => button.addEventListener("click", () => {
    category = button.dataset.category || "all";
    categoryButtons.forEach((item) => item.classList.toggle("active", item === button));
    filterDishes();
  }));

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

  document.addEventListener("workspace:state-change", refreshSelectedOrder);
  document.addEventListener("workspace:busy", (event) => {
    workspaceBusy = event.detail ? true : false;
    if (!workspaceBusy && refreshPending) {
      refreshPending = false;
      refreshSelectedOrder();
    }
  });

  workspace.addEventListener("submit", async (event) => {
    const form = event.target.closest("[data-order-item-form]");
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

  workspace.querySelectorAll("[data-checkout-form]").forEach((form) => {
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

  workspace.querySelectorAll("input[name='guest_count']").forEach((input) => input.addEventListener("input", () => {
    const preview = input.closest("form")?.querySelector("[data-guest-preview]");
    if (preview) preview.textContent = input.value || "1";
  }));

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
