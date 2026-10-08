document.addEventListener("DOMContentLoaded", () => {
    const dishCards = [...document.querySelectorAll("[data-qr-dish]")];
    const itemsElement = document.querySelector("[data-qr-items]");
    const panel = document.querySelector("[data-qr-cart-panel]");
    const menuStart = document.querySelector("[data-qr-menu-start]");
    const menuSections = [...document.querySelectorAll("[data-qr-section]")];
    const searchInput = document.querySelector("[data-qr-search]");
    const searchEmpty = document.querySelector("[data-qr-search-empty]");
    const storageKey = `qlnh-qr-cart-${window.location.pathname}`;
    const countElements = [...document.querySelectorAll("[data-qr-count]")];
    const totalElements = [...document.querySelectorAll("[data-qr-total]")];
    const submitButton = document.querySelector("[data-qr-submit]");
    const submitStatus = document.querySelector("[data-qr-submit-status]");
    const orderReady = submitButton?.dataset.orderReady === "true";
    let isSubmitting = false;
    let cart = {};
    try {
        const storedCart = JSON.parse(sessionStorage.getItem(storageKey) || "{}");
        cart = storedCart && typeof storedCart === "object" && !Array.isArray(storedCart) ? storedCart : {};
    } catch (_error) {
        sessionStorage.removeItem(storageKey);
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
    const save = () => sessionStorage.setItem(storageKey, JSON.stringify(cart));
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
            card.classList.toggle("has-quantity", quantity > 0);
        });
        if (!itemsElement) return;
        itemsElement.innerHTML = "";
        const entries = Object.values(cart);
        if (submitButton) submitButton.disabled = !orderReady || isSubmitting || !entries.length;
        if (!entries.length) {
            itemsElement.innerHTML = '<p class="customer-qr-cart-empty">Chưa có món trong giỏ.</p>';
            return;
        }
        entries.forEach((item) => {
            const row = document.createElement("div");
            row.className = "customer-qr-cart-item";
            row.innerHTML = `<div class="customer-qr-cart-item-head"><strong>${escapeHtml(item.name)}</strong><span>${formatMoney(item.price * item.quantity)}</span></div><div class="customer-qr-quantity"><button type="button" data-qr-decrease="${item.id}" aria-label="Giảm ${escapeHtml(item.name)}">−</button><b>${item.quantity}</b><button type="button" data-qr-increase="${item.id}" aria-label="Tăng ${escapeHtml(item.name)}">+</button></div><label>Ghi chú món<input type="text" maxlength="500" value="${escapeHtml(item.note || "")}" data-qr-note="${item.id}" placeholder="Ví dụ: không hành"></label>`;
            itemsElement.appendChild(row);
        });
    };

    const add = (card) => {
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
        const id = event.target.dataset.qrIncrease || event.target.dataset.qrDecrease;
        if (!id || !cart[id]) return;
        if (event.target.dataset.qrIncrease) cart[id].quantity = Math.min(cart[id].quantity + 1, 100);
        if (event.target.dataset.qrDecrease) cart[id].quantity -= 1;
        if (cart[id].quantity <= 0) delete cart[id];
        save();
        render();
    });
    itemsElement?.addEventListener("input", (event) => {
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
            const response = await fetch(button.dataset.endpoint, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrf,
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: JSON.stringify({ items: entries.map(({ id, quantity, note }) => ({ dish_id: Number(id), quantity, note })) }),
            });
            const responseText = await response.text();
            let result = {};
            try { result = responseText ? JSON.parse(responseText) : {}; } catch (_error) { /* HTML error page */ }
            if (!response.ok) {
                const fallback = response.status === 403
                    ? "Phiên gọi món đã hết hạn. Hãy tải lại mã QR rồi gửi lại."
                    : "Không thể gửi yêu cầu. Vui lòng thử lại.";
                throw new Error(result.error || fallback);
            }
            sessionStorage.removeItem(storageKey);
            cart = {};
            render();
            window.location.href = result.status_url;
        } catch (error) {
            showStatus(error.message || "Không thể gửi yêu cầu. Vui lòng thử lại.");
            isSubmitting = false;
            button.textContent = "Gửi yêu cầu gọi món";
            render();
        }
    });
    render();
});
