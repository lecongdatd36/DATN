document.addEventListener("DOMContentLoaded", () => {
    const service = document.querySelector("[data-qr-service]");
    if (!service) return;
    const status = service.querySelector("[data-service-status]");
    const storageKey = `qlnh-qr-service-${window.location.pathname}`;
    let busy = false;
    let pending = {};
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
        const saved = JSON.parse(storage.getItem(storageKey) || "{}");
        pending = saved && typeof saved === "object" && !Array.isArray(saved) ? saved : {};
    } catch (_error) {
        storage.removeItem(storageKey);
    }

    const requestId = () => {
        if (window.crypto?.randomUUID) return window.crypto.randomUUID();
        const bytes = new Uint8Array(16);
        window.crypto.getRandomValues(bytes);
        bytes[6] = (bytes[6] & 0x0f) | 0x40;
        bytes[8] = (bytes[8] & 0x3f) | 0x80;
        const hex = [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
        return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    };
    const savePending = () => {
        if (Object.keys(pending).length) storage.setItem(storageKey, JSON.stringify(pending));
        else storage.removeItem(storageKey);
    };

    service.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-service-type]");
        if (!button || busy) return;
        busy = true;
        const requestType = button.dataset.serviceType;
        const clientRequestId = pending[requestType] || requestId();
        pending[requestType] = clientRequestId;
        savePending();
        const original = button.textContent;
        button.disabled = true;
        button.textContent = "Đang gửi…";
        if (status) status.textContent = "";
        try {
            const csrf = document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
            const response = await fetch(service.dataset.endpoint, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrf,
                },
                body: JSON.stringify({
                    request_type: requestType,
                    client_request_id: clientRequestId,
                }),
            });
            const responseText = await response.text();
            let payload = {};
            try { payload = responseText ? JSON.parse(responseText) : {}; } catch (_error) { /* HTML error page */ }
            if (!response.ok) {
                if (response.status >= 400 && response.status < 500) {
                    delete pending[requestType];
                    savePending();
                }
                throw new Error(payload.error || "Không thể gửi yêu cầu phục vụ.");
            }
            delete pending[requestType];
            savePending();
            button.classList.add("is-requested");
            button.textContent = "Đã báo";
            if (status) status.textContent = `${payload.request_type}: ${payload.status}.`;
        } catch (error) {
            button.disabled = false;
            button.textContent = original;
            if (status) status.textContent = error.message;
        } finally {
            busy = false;
        }
    });
});
