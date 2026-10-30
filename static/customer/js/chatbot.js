(() => {
    "use strict";
    const root = document.querySelector("[data-customer-chat]");
    if (!root) return;
    const toggle = root.querySelector("[data-chat-toggle]");
    const panel = root.querySelector(".customer-chat-panel");
    const close = root.querySelector("[data-chat-close]");
    const reset = root.querySelector("[data-chat-reset]");
    const form = root.querySelector("[data-chat-form]");
    const input = form.elements.message;
    const status = root.querySelector("[data-chat-status]");
    const messages = root.querySelector("[data-chat-messages]");
    const suggestions = root.querySelector("[data-chat-suggestions]");
    const scroller = root.querySelector("[data-chat-scroll]");
    const csrf = form.querySelector("[name=csrfmiddlewaretoken]").value;
    let busy = false;
    let loaded = false;

    function setBusy(value, label = "") {
        busy = value;
        form.querySelector("button").disabled = value;
        input.disabled = value;
        reset.disabled = value;
        suggestions.querySelectorAll("button").forEach(button => { button.disabled = value; });
        form.setAttribute("aria-busy", String(value));
        status.textContent = label;
    }

    function addMessage(role, text, dishes = [], apriori = []) {
        const bubble = document.createElement("div");
        bubble.className = "customer-chat-message";
        bubble.dataset.role = role;
        const label = document.createElement("span");
        label.className = "customer-chat-message-label";
        label.textContent = role === "user" ? "Bạn" : "Trợ lý QLNH";
        bubble.append(label, document.createTextNode(text));
        function addDish(dish) {
            const item = document.createElement("span");
            item.className = "customer-chat-dish";
            const name = document.createElement("strong");
            name.textContent = dish.name;
            const price = document.createElement("small");
            const amount = Number(dish.price_vnd);
            price.textContent = `${Number.isFinite(amount) ? amount.toLocaleString("vi-VN") : "—"} đồng / ${dish.unit} · ${dish.category} · Đang bán`;
            item.append(name, price);
            bubble.append(item);
        }
        dishes.forEach(addDish);
        if (apriori.length) {
            const heading = document.createElement("strong");
            heading.className = "customer-chat-apriori";
            heading.textContent = "Gợi ý gọi thêm từ Apriori";
            bubble.append(heading);
            apriori.forEach(addDish);
        }
        messages.append(bubble);
        scroller.scrollTop = scroller.scrollHeight;
    }

    async function post(payload) {
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), 35000);
        try {
            const response = await fetch(root.dataset.endpoint, {
                method: "POST", credentials: "same-origin", signal: controller.signal,
                headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
                body: JSON.stringify(payload),
            });
            const data = response.headers.get("content-type")?.includes("application/json") ? await response.json() : {};
            if (!response.ok) {
                throw new Error(data.error || (response.status === 403 ? "Phiên bảo mật đã đổi. Vui lòng tải lại trang." : "Chưa kết nối được trợ lý. Vui lòng thử lại sau."));
            }
            return data;
        } finally {
            window.clearTimeout(timeout);
        }
    }

    async function load(action = "state") {
        if (busy) return;
        setBusy(true, "Đang mở cuộc trò chuyện…");
        try {
            const data = await post({ action });
            messages.replaceChildren();
            for (const item of data.history) addMessage(item.role, item.text);
            suggestions.hidden = data.history.length > 0;
            loaded = true;
            setBusy(false, data.available ? "" : "Trợ lý đang chờ cấu hình API. Bạn vẫn có thể xem thực đơn và đặt bàn.");
        } catch (error) {
            setBusy(false, error.name === "AbortError" ? "Kết nối đang chậm. Vui lòng thử lại sau." : error.message);
        }
    }

    async function send(text) {
        if (busy || !text.trim()) return;
        if (text.length > 1000) { status.textContent = "Câu hỏi tối đa 1.000 ký tự."; return; }
        setBusy(true, "Trợ lý đang trả lời…");
        try {
            const data = await post({ action: "message", message: text.trim() });
            addMessage("user", text.trim());
            addMessage("assistant", data.answer, data.dishes, data.apriori);
            suggestions.hidden = true;
            input.value = "";
            setBusy(false, data.attempts >= data.max_turns ? "Đã đạt giới hạn lượt. Bấm Trò chuyện mới để tiếp tục." : "");
            input.focus();
        } catch (error) {
            setBusy(false, error.name === "AbortError" ? "Kết nối đang chậm. Vui lòng chờ rồi thử lại." : error.message);
        }
    }

    toggle.setAttribute("aria-label", "Mở trò chuyện với QLNH");
    toggle.addEventListener("click", async () => {
        const opening = panel.hidden;
        panel.hidden = !opening;
        toggle.setAttribute("aria-expanded", String(opening));
        toggle.setAttribute("aria-label", opening ? "Thu gọn trò chuyện với QLNH" : "Mở trò chuyện với QLNH");
        if (opening) { close.focus(); if (!loaded) await load(); }
    });
    function hide() {
        panel.hidden = true;
        toggle.setAttribute("aria-expanded", "false");
        toggle.setAttribute("aria-label", "Mở trò chuyện với QLNH");
        toggle.focus();
    }
    close.addEventListener("click", hide);
    panel.addEventListener("keydown", event => { if (event.key === "Escape") hide(); });
    reset.addEventListener("click", () => load("reset"));
    form.addEventListener("submit", event => { event.preventDefault(); send(input.value); });
    input.addEventListener("keydown", event => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); send(input.value); }
    });
    suggestions.querySelectorAll("button").forEach(button => button.addEventListener("click", () => {
        input.value = button.textContent;
        send(input.value);
    }));
})();
