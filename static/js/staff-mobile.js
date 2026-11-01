"use strict";
(() => {
  const app = document.querySelector("[data-mobile-app]");
  if (!app) return;
  const formatter = new Intl.NumberFormat("vi-VN");
  const money = value => formatter.format(Number(value)) + "đ";
  const normalize = value => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[đĐ]/g, "d").toLowerCase().trim();
  const dialog = document.querySelector("[data-confirm-dialog]");
  let busy = false, uncertain = false, navigation = null, lookup = null, quoteRequest = null, searchTimer;
  let pendingNavigation = 0;
  let area = "all", tableStatus = "all", category = "all";
  const names = new WeakMap();
  const root = () => document.querySelector("#mobile-page");
  const feedback = message => {
    const node = document.querySelector("#mobile-feedback");
    node.textContent = message;
    node.hidden = !message;
  };
  const offerRefresh = message => {
    feedback(message);
    document.querySelector("[data-refresh]").hidden = false;
  };
  function filterTables() {
    let count = 0;
    app.querySelectorAll("[data-table-card]").forEach(card => {
      const statusMatches = tableStatus === "all" || (tableStatus === "payment" ? card.dataset.payment.includes("yes") : card.dataset.status === tableStatus);
      card.hidden = !(statusMatches && (area === "all" || card.dataset.areaId === area));
      if (!card.hidden) count++;
    });
    const empty = app.querySelector("[data-no-tables]");
    if (empty) empty.hidden = count > 0;
  }
  function filterDishes() {
    const query = normalize(app.querySelector("[data-dish-search]")?.value || "");
    let count = 0;
    app.querySelectorAll("[data-inline-add]").forEach(card => {
      if (!names.has(card)) names.set(card, normalize(card.dataset.name || ""));
      const hidden = !((category === "all" || category === card.dataset.categoryId) && names.get(card).includes(query));
      if (card.hidden !== hidden) card.hidden = hidden;
      if (!hidden) count++;
    });
    const empty = app.querySelector("[data-no-dishes]");
    if (empty) empty.hidden = count > 0;
  }
  function paymentFields() {
    const form = app.querySelector("[data-payment-form]");
    if (!form) return;
    const cash = form.querySelector("[name=payment_method]:checked")?.value === "CASH";
    form.querySelector("[data-cash-fields]").hidden = !cash;
    form.querySelector("[data-bank-fields]").hidden = cash;
    form.querySelectorAll("[data-cash-fields] input").forEach(input => {input.disabled = !cash;});
    form.querySelectorAll("[data-bank-fields] input").forEach(input => {input.disabled = cash;});
    form.querySelector("[name=cash_received]").required = cash;
    form.querySelector("[name=received_transfer]").required = !cash;
    const given = Number(form.querySelector("[name=cash_received]").value || 0);
    form.querySelector("[data-change]").textContent = money(Math.max(0, given - Number(form.dataset.due)));
  }
  function init(menuCategory = "all") {
    category = menuCategory === "all" || [...app.querySelectorAll("[data-category]")].some(button => button.dataset.category === menuCategory) ? menuCategory : "all";
    filterTables();
    filterDishes();
    paymentFields();
    document.dispatchEvent(new CustomEvent("mobile:page-ready"));
    for (const [attribute, current] of [["data-area", area], ["data-table-status", tableStatus], ["data-category", category]]) {
      app.querySelectorAll(`[${attribute}]`).forEach(button => {
        const active = button.getAttribute(attribute) === current;
        button.classList.toggle("active", active);button.setAttribute("aria-pressed", String(active));
      });
    }
  }
  function snapshot() {
    const page = root(), values = new Map();
    page.querySelectorAll("[data-preserve]").forEach(input => {
      if (input.value !== input.defaultValue) values.set(input.id || `${input.closest("[data-state-key]")?.dataset.stateKey}:${input.name}`, input.value);
    });
    return {page: page.dataset.page, order: page.dataset.order, values, menu: page.dataset.page === "menu" ? {category, query: page.querySelector("[data-dish-search]")?.value || ""} : null, method: page.querySelector("[name=payment_method]:checked")?.value};
  }
  async function navigate(url, {replace = false, keepScroll = false, preserve = false} = {}) {
    navigation?.abort();lookup?.abort();quoteRequest?.abort();
    const controller = new AbortController();navigation = controller;
    const saved = preserve ? snapshot() : null, scroll = window.scrollY;
    const response = await fetch(url, {credentials: "same-origin", cache: "no-store", signal: controller.signal});
    if (response.redirected && !new URL(response.url).pathname.startsWith(new URL(app.dataset.mobileUrl || window.location.href).pathname)) {
      window.location.assign(response.url);return;
    }
    if (!response.ok) throw new Error(response.status === 403 ? "Quyền truy cập đã thay đổi. Hãy đăng nhập lại hoặc quay về khu vực được cấp quyền." : "Chưa tải được nội dung. Hãy thử cập nhật lại.");
    const next = new DOMParser().parseFromString(await response.text(), "text/html").querySelector("#mobile-page");
    if (!next) throw new Error("Phiên làm việc đã thay đổi. Hãy tải lại trang.");
    root().replaceWith(next);
    const samePage = saved && saved.page === next.dataset.page && saved.order === next.dataset.order;
    if (samePage) {
      next.querySelectorAll("[data-preserve]").forEach(input => {
        const key = input.id || `${input.closest("[data-state-key]")?.dataset.stateKey}:${input.name}`;
        if (saved.values.has(key)) {
          input.value = saved.values.get(key);
          if (input.value !== input.defaultValue) next.dataset.dirty = "true";
        }
      });
      const search = next.querySelector("[data-dish-search]");
      if (saved.menu && search) search.value = saved.menu.query;
      next.querySelectorAll("[name=payment_method]").forEach(input => {input.checked = input.value === saved.method;});
    }
    history[replace ? "replaceState" : "pushState"]({}, "", url);
    uncertain = false;feedback("");document.querySelector("[data-refresh]").hidden = true;
    init(samePage && saved.menu ? saved.menu.category : "all");window.scrollTo({top: keepScroll ? scroll : 0, behavior: "instant"});
    const hash = new URL(url, location.href).hash.slice(1);
    if (hash) document.getElementById(decodeURIComponent(hash))?.scrollIntoView({block: "start"});
  }
  const navigateSafely = (url, options) => {
    pendingNavigation++;
    return navigate(url, options)
      .catch(error => {if (error.name !== "AbortError") offerRefresh(error.message);})
      .finally(() => { pendingNavigation--; });
  };
  async function confirm(form) {
    if (!form.dataset.confirm) return true;
    let text = form.dataset.confirm;
    if (form.matches("[data-payment-form]")) {
      const cash = form.querySelector("[name=payment_method]:checked").value === "CASH";
      text += `\nCần thu: ${money(form.dataset.due)}\nPhương thức: ${cash ? "Tiền mặt" : "Chuyển khoản"}`;
      if (cash) text += `\nKhách đưa: ${money(form.querySelector("[name=cash_received]").value)}\nTiền thừa: ${form.querySelector("[data-change]").textContent}`;
    }
    dialog.querySelector("[data-confirm-copy]").textContent = text;
    dialog.returnValue = "";dialog.showModal();
    return new Promise(resolve => dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), {once: true}));
  }
  async function submit(form) {
    if (busy || dialog.open) return;
    if (uncertain) {offerRefresh("Chưa rõ kết quả thao tác trước. Cập nhật order để kiểm tra trước khi thực hiện tiếp.");return;}
    const customerForm = form.matches("[data-open-form]");
    if (customerForm && form.elements.customer_phone.value.trim() && form.dataset.verifiedPhone !== form.elements.customer_phone.value.trim()) {
      feedback("Bấm Tìm để đối chiếu SĐT trước khi mở bàn.");return;
    }
    if (!form.reportValidity() || !await confirm(form)) return;
    // Multiple submit events can be waiting on a confirmation dialog.
    if (busy) return;
    const data = new FormData(form), action = new URL(form.action).pathname.split("/").filter(Boolean).pop();
    busy = true;root().inert = true;
    document.dispatchEvent(new CustomEvent("workspace:busy", {detail: true}));
    const controller = new AbortController(), timeout = window.setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(form.action, {method: "POST", body: data, credentials: "same-origin", signal: controller.signal, headers: {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}});
      const payload = await response.json().catch(() => null);
      if (!payload) throw new Error("Chưa nhận được kết quả thao tác. Cập nhật để kiểm tra order trước khi thử lại.");
      if (!response.ok || !payload.ok) {
        offerRefresh(payload.error || "Chưa thể thực hiện thao tác.");return;
      }
      if (form.matches("[data-inline-add]")) {
        app.querySelectorAll("[name=expected_revision]").forEach(input => {input.value = payload.revision;});
        app.querySelectorAll("[data-order-due]").forEach(node => {node.textContent = money(payload.due);});
        const badge = form.querySelector("[data-dish-count]");badge.textContent = Number(badge.textContent || 0) + Number(data.get("quantity") || 1);badge.hidden = false;
        form.elements.note.value = "";form.querySelector("details").open = false;
        const count = app.querySelector("[data-draft-count]");if (count) count.textContent = `${payload.draft_count} món mới chưa gửi`;
        feedback("");
      } else {
        await navigate(payload.url, {replace: true, keepScroll: ["edit", "served", "cancel-item"].includes(action), preserve: action === "edit"});
      }
      document.dispatchEvent(new CustomEvent("workspace:mutation"));
    } catch (error) {
      uncertain = true;offerRefresh(error.name === "AbortError" ? "Chưa nhận được kết quả. Cập nhật để kiểm tra order trước khi thao tác tiếp." : error.message);
    } finally {
      window.clearTimeout(timeout);busy = false;root().inert = false;
      document.dispatchEvent(new CustomEvent("workspace:busy", {detail: false}));
    }
  }
  async function findCustomer() {
    const form = app.querySelector("[data-open-form]");
    if (!form) return;
    lookup?.abort();const controller = new AbortController();lookup = controller;
    const phone = form.elements.customer_phone, result = form.querySelector("[data-customer-result]"), newCustomer = form.querySelector("[data-new-customer]");
    delete form.dataset.verifiedPhone;newCustomer.hidden = true;form.elements.customer_name.required = false;
    if (!phone.value.trim()) {result.textContent = "Không cung cấp SĐT: tiếp tục phục vụ khách vãng lai.";return;}
    const requested = phone.value;result.textContent = "Đang tìm hồ sơ…";
    try {
      const url = new URL(app.dataset.lookupUrl, location.origin);url.searchParams.set("phone", requested);
      const response = await fetch(url, {signal: controller.signal, credentials: "same-origin", cache: "no-store"});
      const payload = await response.json();
      if (phone.value !== requested) return;
      if (!response.ok || !payload.ok) throw new Error(payload.error || "Chưa tra cứu được khách hàng.");
      phone.value = payload.found ? payload.customer.phone : payload.phone;form.dataset.verifiedPhone = phone.value;
      if (payload.found) {
        const customer = payload.customer;
        result.textContent = `${customer.name} · ${customer.phone} · Hạng ${customer.tier} · Ưu đãi ${customer.discount_percent}%`;
        form.elements.customer_name.value = "";
      } else {
        result.textContent = "Chưa có hồ sơ với SĐT này. Nhập tên nếu khách muốn đăng ký.";
        newCustomer.hidden = false;form.elements.customer_name.required = true;
      }
    } catch (error) {if (error.name !== "AbortError") result.textContent = error.message || "Chưa có kết nối để tra cứu. Không tự tạo hồ sơ khi chưa đối chiếu.";}
  }
  async function applyPromotion() {
    const form = app.querySelector("[data-payment-form]");
    if (!form || busy) return;
    quoteRequest?.abort();const controller = new AbortController();quoteRequest = controller;
    const url = new URL(app.dataset.quoteUrl, location.origin), requested = form.elements.promotion_code.value.trim().toUpperCase();
    url.searchParams.set("order", form.elements.order_id.value);url.searchParams.set("promotion", requested);
    const status = form.querySelector("[data-promotion-feedback]"), button = form.querySelector("[type=submit]");
    button.disabled = true;status.textContent = "Đang kiểm tra ưu đãi…";
    try {
      const response = await fetch(url, {credentials: "same-origin", cache: "no-store", signal: controller.signal});
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.error || "Chưa kiểm tra được mã.");
      if (String(payload.revision) !== form.elements.expected_revision.value) throw new Error("Order đã thay đổi. Cập nhật trước khi thu tiền.");
      form.elements.promotion_code.value = payload.promotion;form.elements.reviewed_total.value = payload.due;form.dataset.due = payload.due;
      app.querySelectorAll("[data-order-due]").forEach(node => {node.textContent = money(payload.due);});
      app.querySelector("[data-subtotal]").textContent = money(payload.subtotal);app.querySelector("[data-discount]").textContent = "−" + money(payload.discount);
      form.elements.cash_received.min = payload.due;form.elements.received_transfer.checked = false;
      status.textContent = payload.promotion ? "Đã áp dụng ưu đãi. Kiểm tra lại số cần thu." : "Đã cập nhật tạm tính.";paymentFields();
    } catch (error) {if (error.name !== "AbortError") offerRefresh(error.message || "Chưa cập nhật được ưu đãi.");}
    finally {if (quoteRequest === controller) button.disabled = false;}
  }
  document.addEventListener("click", event => {
    const link = event.target.closest("[data-mobile-link]");
    if (link && !event.ctrlKey && !event.metaKey && !event.shiftKey && event.button === 0) {
      event.preventDefault();if (!busy) navigateSafely(link.href);return;
    }
    const step = event.target.closest("[data-step]");
    if (step && !busy) {
      const form = step.closest("form"), input = form.elements.quantity;
      input.value = String(Math.min(Number(input.max), Math.max(Number(input.min), Number(input.value || 1) + Number(step.dataset.step))));form.requestSubmit();return;
    }
    const filter = event.target.closest("[data-area],[data-table-status],[data-category]");
    if (filter) {
      const key = filter.hasAttribute("data-area") ? "data-area" : filter.hasAttribute("data-table-status") ? "data-table-status" : "data-category";
      const value = filter.getAttribute(key);if (key === "data-area") area = value;else if (key === "data-table-status") tableStatus = value;else category = value;
      filter.parentElement.querySelectorAll("button").forEach(button => {button.classList.toggle("active", button === filter);button.setAttribute("aria-pressed", String(button === filter));});
      key === "data-category" ? filterDishes() : filterTables();return;
    }
    if (event.target.closest("[data-refresh]") && !busy) navigateSafely(location.href, {replace: true, keepScroll: true, preserve: true});
    if (event.target.closest("[data-customer-find]")) findCustomer();
    if (event.target.closest("[data-apply-promotion]")) applyPromotion();
    if (event.target.closest("[data-customer-clear]")) {
      const form = app.querySelector("[data-open-form]");form.elements.customer_phone.value = "";form.elements.customer_phone.dispatchEvent(new Event("input", {bubbles: true}));
    }
  });
  document.addEventListener("submit", event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.closest("[data-mobile-app]")) return;
    event.preventDefault();
    if (form.method.toLowerCase() === "get") {
      const url = new URL(form.action);url.search = new URLSearchParams(new FormData(form)).toString();navigateSafely(url.href);return;
    }
    submit(form);
  });
  document.addEventListener("input", event => {
    const input = event.target;
    if (input.matches("[data-dish-search]")) {clearTimeout(searchTimer);searchTimer = window.setTimeout(filterDishes, 120);return;}
    if (!input.closest("[data-mobile-app]")) return;
    root().dataset.dirty = "true";
    if (input.matches("[name=cash_received]")) paymentFields();
    if (input.matches("[data-customer-phone]")) {
      lookup?.abort();const form = input.form;delete form.dataset.verifiedPhone;
      form.elements.customer_name.value = "";form.elements.customer_name.required = false;form.querySelector("[data-new-customer]").hidden = true;
      form.querySelector("[data-customer-result]").textContent = input.value.trim() ? "Bấm Tìm để đối chiếu SĐT trước khi mở bàn." : "Không cung cấp SĐT: mở bàn không tạo hồ sơ khách.";
      form.querySelector("[data-customer-clear]").hidden = !input.value.trim();
    }
  });
  document.addEventListener("change", event => {
    if (event.target.matches("[name=payment_method]")) paymentFields();
    if (event.target.matches(".m-stepper [name=quantity]") && !busy) event.target.form.requestSubmit();
  });
  window.addEventListener("popstate", () => {if (!busy) navigateSafely(location.href, {replace: true});});
  document.addEventListener("workspace:state-change", () => {
    if (document.hidden) return;
    // A background refresh must not replace the destination of a menu click.
    if (pendingNavigation) return;
    if (busy || document.querySelector("dialog[open]") || root().dataset.dirty === "true" || ["menu", "checkout"].includes(root().dataset.page) || app.contains(document.activeElement) && /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) {
      document.querySelector("[data-refresh]").hidden = false;return;
    }
    navigateSafely(location.href, {replace: true, keepScroll: true});
  });
  init();
})();
