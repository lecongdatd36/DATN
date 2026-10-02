document.addEventListener("DOMContentLoaded", () => {
    const dishCards = [...document.querySelectorAll("[data-qr-dish]")];
    const itemsElement = document.querySelector("[data-qr-items]");
    const panel = document.querySelector("[data-qr-cart-panel]");
    const storageKey = `qlnh-qr-cart-${window.location.pathname}`;
    const countElements = [...document.querySelectorAll("[data-qr-count]")];
    const totalElements = [...document.querySelectorAll("[data-qr-total]")];
    let cart = JSON.parse(sessionStorage.getItem(storageKey) || "{}");

    const formatMoney = (value) => `${new Intl.NumberFormat("vi-VN").format(value)}đ`;
    const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "'": "&#39;",
        '"': "&quot;",
    })[character]);
    const save = () => sessionStorage.setItem(storageKey, JSON.stringify(cart));
    const summary = () => Object.values(cart).reduce((result, item) => ({
        count: result.count + item.quantity,
        total: result.total + item.price * item.quantity,
    }), { count: 0, total: 0 });

    const render = () => {
        const { count, total } = summary();
        countElements.forEach((element) => { element.textContent = count; });
        totalElements.forEach((element) => { element.textContent = formatMoney(total); });
        if (!itemsElement) return;
        itemsElement.innerHTML = "";
        const entries = Object.values(cart);
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
        document.querySelector("[data-qr-submit]").disabled = false;
    };

    const add = (card) => {
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
        dishCards.forEach((card) => { card.hidden = button.dataset.qrCategory !== "all" && card.dataset.category !== button.dataset.qrCategory; });
    }));
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
    document.querySelector("[data-qr-cart-open]")?.addEventListener("click", () => panel?.classList.add("is-open"));
    document.querySelector("[data-qr-cart-close]")?.addEventListener("click", () => panel?.classList.remove("is-open"));
    document.querySelector("[data-qr-submit]")?.addEventListener("click", async (event) => {
        const button = event.currentTarget;
        const entries = Object.values(cart);
        if (!entries.length) return;
        button.disabled = true;
        button.textContent = "Đang gửi...";
        try {
            const csrf = document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
            const response = await fetch(button.dataset.endpoint, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
                body: JSON.stringify({ items: entries.map(({ id, quantity, note }) => ({ dish_id: Number(id), quantity, note })) }),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || "Không thể gửi yêu cầu.");
            sessionStorage.removeItem(storageKey);
            cart = {};
            render();
            window.location.href = result.status_url;
        } catch (error) {
            window.alert(error.message);
            button.disabled = false;
            button.textContent = "Gửi yêu cầu gọi món";
        }
    });
    render();
});