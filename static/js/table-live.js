"use strict";

(() => {
    const root = document.querySelector("[data-table-live]");
    if (!root) return;
    const message = root.querySelector("[data-live-message]");
    const filters = root.querySelector("[data-table-filters]");
    const manual = root.querySelector("[data-live-refresh]");
    let timer;
    let controller;
    let stopped = false;
    const normalMessage = "Tự cập nhật mỗi 15 giây khi đang xem trang.";
    message.textContent = normalMessage;

    function schedule() {
        clearTimeout(timer);
        if (!stopped && !document.hidden) timer = setTimeout(refresh, 15000);
    }

    async function refresh() {
        const current = root.querySelector("#table-live-results");
        if (stopped || controller || document.hidden) return;
        if (filters.contains(document.activeElement) || current.contains(document.activeElement)) {
            schedule();
            return;
        }
        controller = new AbortController();
        const timeout = setTimeout(() => controller?.abort(), 10000);
        try {
            const response = await fetch(window.location.href, {
                headers: {"X-Table-Refresh": "1"}, credentials: "same-origin",
                cache: "no-store", signal: controller.signal,
            });
            if (response.redirected || response.status === 401 || response.status === 403) {
                stopped = true;
                message.textContent = "Phiên đăng nhập hoặc quyền truy cập đã thay đổi. Hãy tải lại trang.";
                return;
            }
            if (!response.ok) throw new Error("Unable to refresh");
            const html = await response.text();
            const parsed = new DOMParser().parseFromString(html, "text/html");
            const replacement = parsed.querySelector("#table-live-results");
            if (!replacement) throw new Error("Missing table results");
            if (!document.hidden && !stopped && !current.contains(document.activeElement)) {
                current.replaceWith(replacement);
                message.textContent = normalMessage;
            }
        } catch (_) {
            if (!document.hidden && !stopped) message.textContent = "Chưa cập nhật được; đang hiển thị dữ liệu lần trước. Hệ thống sẽ thử lại.";
        } finally {
            clearTimeout(timeout);
            controller = undefined;
            schedule();
        }
    }

    manual.addEventListener("click", (event) => {
        if (stopped) return;
        event.preventDefault();
        clearTimeout(timer);
        refresh();
    });
    document.addEventListener("visibilitychange", () => {
        clearTimeout(timer);
        if (document.hidden) controller?.abort();
        else refresh();
    });
    window.addEventListener("pagehide", () => {
        stopped = true;
        clearTimeout(timer);
        controller?.abort();
    });
    window.addEventListener("pageshow", (event) => {
        if (event.persisted) {
            stopped = false;
            refresh();
        }
    });
    schedule();
})();
