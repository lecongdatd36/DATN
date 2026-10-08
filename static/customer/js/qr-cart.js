document.addEventListener("DOMContentLoaded", () => {
    const dishCards = [...document.querySelectorAll("[data-qr-dish]")];
    const itemsElement = document.querySelector("[data-qr-items]");
    const panel = document.querySelector("[data-qr-cart-panel]");
    const menuStart = document.querySelector("[data-qr-menu-start]");
    const menuSections = [...document.querySelectorAll("[data-qr-section]")];
    const searchInput = document.querySelector("[data-qr-search]");
    const searchEmpty = document.querySelector("[data-qr-search-empty]");
    const page = document.querySelector("[data-qr-menu-page]");
    const storageKey = `qlnh-qr-cart-${window.location.pathname}`;
    const storageTtl = 12 * 60 * 60 * 1000;
    const countElements = [...document.querySelectorAll("[data-qr-count]")];
    const totalElements = [...document.querySelectorAll("[data-qr-total]")];
    const submitButton = document.querySelector("[data-qr-submit]");
    const submitStatus = document.querySelector("[data-qr-submit-status]");
    const orderReady = submitButton?.dataset.orderReady === "true";
    let isSubmitting = false;
    let cart = {};
    let pendingSubmission = null;
    const storage = (() => {
        try {
            const probe = `${storageKey}-probe`;
            localStorage.setItem(probe, "1");
            localStorage.removeItem(probe);
            return localStorage;
        } catch (_error) {
            return sessionStorage;
        }
    })();
    try {
        let stored = JSON.parse(storage.getItem(storageKey) || "null");
        if (!stored && storage !== sessionStorage) {
            const legacy = JSON.parse(sessionStorage.getItem(storageKey) || "null");
            if (legacy) stored = {savedAt: Date.now(), cart: legacy, pending: null};
        }
        if (stored?.savedAt && Date.now() - stored.savedAt <= storageTtl) {
            cart = stored.cart && typeof stored.cart === "object" && !Array.isArray(stored.cart) ? stored.cart : {};
            pendingSubmission = stored.pending || null;
        } else {
            storage.removeItem(storageKey);
        }
    } catch (_error) {
        storage.removeItem(storageKey);
    }

    const formatMoney = (value) => `${new Intl.NumberFormat("vi-VN").format(value)}đ`;
    const normalizeText = (value) => String(value || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .replace(/đ/g, "d")
        .trim();
    const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "'": "&#39;",
        '"': "&quot;",
    })[character]);
    const save = () => storage.setItem(storageKey, JSON.stringify({
        savedAt: Date.now(),
        cart,
        pending: pendingSubmission,
    }));
    const requestId = () => {
        if (window.crypto?.randomUUID) return window.crypto.randomUUID();
        const bytes = new Uint8Array(16);
        window.crypto.getRandomValues(bytes);
        bytes[6] = (bytes[6] & 0x0f) | 0x40;
        bytes[8] = (bytes[8] & 0x3f) | 0x80;
        const hex = [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
        return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    };
    const showStatus = (message = "") => {
        if (!submitStatus) return;
        submitStatus.textContent = message;
        submitStatus.hidden = !message;
    };
    const summary = () => Object.values(cart).reduce((result, item) => ({
        count: result.count + item.quantity,
        total: result.total + item.price * item.quantity,
    }), { count: 0, total: 0 });

    const render = () => {
        const { count, total } = summary();
        const frozen = Boolean(pendingSubmission);
        countElements.forEach((element) => { element.textContent = count; });
        totalElements.forEach((element) => { element.textContent = formatMoney(total); });
        dishCards.forEach((card) => {
            const quantity = cart[card.dataset.id]?.quantity || 0;
            const quantityElement = card.querySelector("[data-qr-card-quantity]");
            const plusElement = card.querySelector("[data-qr-add] > span");
            if (quantityElement) {
                quantityElement.textContent = quantity;
                quantityElement.hidden = quantity === 0;
            }
            if (plusElement) plusElement.hidden = quantity > 0;
            const addButton = card.querySelector("[data-qr-add]");
            if (addButton) addButton.disabled = frozen;
            card.classList.toggle("has-quantity", quantity > 0);
        });
        if (!itemsElement) return;
        itemsElement.innerHTML = "";
        const entries = Object.values(cart);
        if (submitButton) {
            submitButton.disabled = !orderReady || isSubmitting || !entries.length;
            if (!isSubmitting) submitButton.textContent = frozen ? "Kiểm tra / gửi lại yêu cầu" : "Gửi yêu cầu gọi món";
        }
        if (!entries.length) {
            itemsElement.innerHTML = '<p class="customer-qr-cart-empty">Chưa có món trong giỏ.</p>';
            return;
        }
        entries.forEach((item) => {
            const row = document.createElement("div");
            row.className = "customer-qr-cart-item";
            const disabled = frozen ? " disabled" : "";
            row.innerHTML = `<div class="customer-qr-cart-item-head"><strong>${escapeHtml(item.name)}</strong><span>${formatMoney(item.price * item.quantity)}</span></div><div class="customer-qr-quantity"><button type="button" data-qr-decrease="${item.id}" aria-label="Giảm ${escapeHtml(item.name)}"${disabled}>−</button><b>${item.quantity}</b><button type="button" data-qr-increase="${item.id}" aria-label="Tăng ${escapeHtml(item.name)}"${disabled}>+</button></div><label>Ghi chú món<input type="text" maxlength="500" value="${escapeHtml(item.note || "")}" data-qr-note="${item.id}" placeholder="Ví dụ: không hành"${disabled}></label>`;
            itemsElement.appendChild(row);
        });
    };

    const add = (card) => {
        if (pendingSubmission) return;
        showStatus();
        const id = card.dataset.id;
        const item = cart[id] || { id, name: card.dataset.name, price: Number(card.dataset.price), quantity: 0, note: "" };
        item.quantity = Math.min(item.quantity + 1, 100);
        cart[id] = item;
        save();
        render();
    };

    document.querySelectorAll("[data-qr-add]").forEach((button) => button.addEventListener("click", () => add(button.closest("[data-qr-dish]"))));
    document.querySelectorAll("[data-qr-category]").forEach((button) => button.addEventListener("click", () => {
        document.querySelectorAll("[data-qr-category]").forEach((item) => item.classList.remove("is-selected"));
        button.classList.add("is-selected");
        const target = button.dataset.qrCategory === "all"
            ? menuStart
            : document.getElementById(`qr-category-${button.dataset.qrCategory}`);
        target?.scrollIntoView({ behavior: "smooth", block: "start" });
    }));
    searchInput?.addEventListener("input", (event) => {
        const query = normalizeText(event.currentTarget.value);
        dishCards.forEach((card) => {
            card.hidden = Boolean(query) && !normalizeText(card.dataset.search).includes(query);
        });
        menuSections.forEach((section) => {
            section.hidden = !section.querySelector("[data-qr-dish]:not([hidden])");
        });
        if (searchEmpty) searchEmpty.hidden = dishCards.some((card) => !card.hidden);
    });
    itemsElement?.addEventListener("click", (event) => {
        if (pendingSubmission) return;
        const id = event.target.dataset.qrIncrease || event.target.dataset.qrDecrease;
        if (!id || !cart[id]) return;
        if (event.target.dataset.qrIncrease) cart[id].quantity = Math.min(cart[id].quantity + 1, 100);
        if (event.target.dataset.qrDecrease) cart[id].quantity -= 1;
        if (cart[id].quantity <= 0) delete cart[id];
        save();
        render();
    });
    itemsElement?.addEventListener("input", (event) => {
        if (pendingSubmission) return;
        const id = event.target.dataset.qrNote;
        if (id && cart[id]) { cart[id].note = event.target.value; save(); }
    });
    document.querySelectorAll("[data-qr-cart-open]").forEach((button) => button.addEventListener("click", () => panel?.classList.add("is-open")));
    document.querySelector("[data-qr-cart-close]")?.addEventListener("click", () => panel?.classList.remove("is-open"));
    submitButton?.addEventListener("click", async (event) => {
        const button = event.currentTarget;
        const entries = Object.values(cart);
        if (!entries.length || isSubmitting) return;
        isSubmitting = true;
        showStatus();
        render();
        button.textContent = "Đang gửi...";
        try {
            const csrf = document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
            if (!pendingSubmission) {
                pendingSubmission = {
                    client_request_id: requestId(),
                    items: entries.map(({ id, quantity, note }) => ({dish_id: Number(id), quantity, note})),
                };
                save();
            }
            const response = await fetch(button.dataset.endpoint, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrf,
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: JSON.stringify(pendingSubmission),
            });
            const responseText = await response.text();
            let result = {};
            try { result = responseText ? JSON.parse(responseText) : {}; } catch (_error) { /* HTML error page */ }
            if (!response.ok) {
                if (response.status >= 400 && response.status < 500) {
                    pendingSubmission = null;
                    save();
                }
                const fallback = response.status === 403
                    ? "Phiên gọi món đã hết hạn. Hãy tải lại mã QR rồi gửi lại."
                    : "Không thể gửi yêu cầu. Vui lòng thử lại.";
                throw new Error(result.error || fallback);
            }
            storage.removeItem(storageKey);
            sessionStorage.removeItem(storageKey);
            cart = {};
            pendingSubmission = null;
            render();
            window.location.href = result.status_url;
        } catch (error) {
            showStatus(error.message || "Không thể gửi yêu cầu. Vui lòng thử lại.");
            isSubmitting = false;
            render();
        }
    });
    if (!pendingSubmission) {
        const availableIds = new Set(dishCards.filter((card) => card.dataset.available === "true").map((card) => card.dataset.id));
        Object.keys(cart).forEach((id) => { if (!availableIds.has(id)) delete cart[id]; });
        save();
    } else {
        showStatus("Yêu cầu trước có thể đã tới hệ thống. Bấm “Kiểm tra / gửi lại” để xác nhận, hệ thống sẽ không tạo trùng.");
    }

    const pollMenuState = async () => {
        if (!page?.dataset.menuStateUrl || !orderReady || document.hidden) return;
        try {
            const response = await fetch(page.dataset.menuStateUrl, {headers: {Accept: "application/json"}, cache: "no-store"});
            if (!response.ok) return;
            const state = await response.json();
            if (!state.ready || state.menu_version !== page.dataset.menuVersion) window.location.reload();
        } catch (_error) {
            // The persisted cart remains available while the network is interrupted.
        }
    };
    window.setInterval(pollMenuState, 15000);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) pollMenuState(); });
    render();
});
