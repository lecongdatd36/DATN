"use strict";

(function () {
    const sidebarKey = "qlnh.sidebarMini";
    const themeKey = "qlnh.colorTheme";
    const desktopQuery = window.matchMedia("(min-width: 992px)");
    const mobileTableQuery = window.matchMedia("(max-width: 767.98px)");
    const mobileLogin = document.querySelector("[data-mobile-login]");
    if (mobileLogin) {
        const syncMobileLogin = () => { mobileLogin.value = mobileTableQuery.matches ? "1" : "0"; };
        syncMobileLogin();
        mobileTableQuery.addEventListener?.("change", syncMobileLogin);
    }
    const body = document.body;
    const sidebarToggle = document.querySelector("[data-sidebar-toggle]");
    const sidebarClosers = document.querySelectorAll("[data-sidebar-close]");
    const sidebarLinks = document.querySelectorAll(".sidebar-link");
    const themeToggles = document.querySelectorAll("[data-theme-toggle]");
    const actionDialog = document.querySelector("[data-action-dialog]");
    const liveClock = document.querySelector("[data-live-clock]");
    const liveDate = document.querySelector("[data-live-date]");
    const pageTitle = document.querySelector("[data-page-title]");
    let pendingAction = null;

    function updateTopbar() {
        const now = new Date();
        if (liveClock) liveClock.textContent = new Intl.DateTimeFormat("vi-VN", {hour: "2-digit", minute: "2-digit"}).format(now);
        if (liveDate) liveDate.textContent = new Intl.DateTimeFormat("vi-VN", {weekday: "long", day: "2-digit", month: "2-digit", year: "numeric"}).format(now);
        if (pageTitle) {
            const title = document.title.split("·")[0].trim();
            if (title) pageTitle.textContent = title;
        }
    }

    function csrfToken() {
        const field = document.querySelector("input[name='csrfmiddlewaretoken']");
        if (field?.value) return field.value;
        const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    function closeActionDialog() {
        if (actionDialog?.open) actionDialog.close();
        const confirmButton = actionDialog?.querySelector("[data-dialog-confirm]");
        if (confirmButton) confirmButton.disabled = false;
        pendingAction = null;
    }

    function openActionDialog(trigger) {
        if (!actionDialog) return;
        pendingAction = trigger;
        const needsReason = trigger.dataset.confirmReason === "true";
        const reasonWrap = actionDialog.querySelector("[data-dialog-reason-wrap]");
        const reason = actionDialog.querySelector("[data-dialog-reason]");
        const error = actionDialog.querySelector("[data-dialog-reason-error]");
        actionDialog.dataset.tone = trigger.dataset.confirmTone || "warning";
        actionDialog.querySelector("[data-dialog-title]").textContent = trigger.dataset.confirmTitle || "Xác nhận thao tác";
        actionDialog.querySelector("[data-dialog-message]").textContent = trigger.dataset.confirmMessage || "Thao tác này sẽ cập nhật dữ liệu ngay lập tức.";
        actionDialog.querySelector("[data-dialog-confirm]").textContent = trigger.dataset.confirmLabel || "Tiếp tục";
        reasonWrap.hidden = !needsReason;
        reason.value = "";
        error.hidden = true;
        actionDialog.showModal();
        (needsReason ? reason : actionDialog.querySelector("[data-dialog-confirm]")).focus();
    }

    function isInlineServedTransition(trigger, actionUrl) {
        try {
            const path = new URL(actionUrl, window.location.origin).pathname;
            return /^\/don-hang\/\d+\/mon\/\d+\/SERVED\/$/.test(path);
        } catch (_) {
            return false;
        }
    }

    function updateInlineServedTransition(trigger, payload) {
        const row = trigger.closest("tr");
        const statusCell = row?.querySelector("td:nth-child(5)");
        if (statusCell) statusCell.textContent = payload.item_status_label;
        row?.classList.add("is-updated");
        const actionGroup = trigger.closest(".d-flex");
        trigger.remove();
        if (actionGroup && !actionGroup.children.length) actionGroup.textContent = "—";
        document.querySelectorAll("[data-confirm-action][data-revision]").forEach((item) => {
            item.dataset.revision = String(payload.order_revision);
        });
    }

    async function submitPendingAction() {
        if (!pendingAction) return;
        const trigger = pendingAction;
        const reason = actionDialog.querySelector("[data-dialog-reason]");
        const needsReason = trigger.dataset.confirmReason === "true";
        if (needsReason && !reason.value.trim()) {
            actionDialog.querySelector("[data-dialog-reason-error]").hidden = false;
            reason.focus();
            return;
        }
        const actionUrl = trigger.dataset.actionUrl || trigger.getAttribute("href") || trigger.getAttribute("formaction");
        const fields = {
            csrfmiddlewaretoken: csrfToken(),
            expected_revision: trigger.dataset.revision || "",
            expected_status: trigger.dataset.status || "",
            order_id: trigger.dataset.orderId || "",
            reason: needsReason ? reason.value.trim() : (trigger.dataset.reason || ""),
        };
        const confirmButton = actionDialog.querySelector("[data-dialog-confirm]");
        confirmButton.disabled = true;
        confirmButton.textContent = "Đang xử lý...";

        if (isInlineServedTransition(trigger, actionUrl)) {
            const data = new FormData();
            Object.entries(fields).forEach(([name, value]) => {
                if (value) data.append(name, value);
            });
            try {
                const response = await fetch(actionUrl, {
                    method: "POST",
                    body: data,
                    credentials: "same-origin",
                    headers: {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
                });
                const payload = await response.json().catch(() => null);
                if (!response.ok || !payload?.ok) throw new Error(payload?.error || "Không thể cập nhật trạng thái món.");
                updateInlineServedTransition(trigger, payload);
                closeActionDialog();
            } catch (error) {
                actionDialog.querySelector("[data-dialog-message]").textContent = error.message;
                confirmButton.disabled = false;
                confirmButton.textContent = trigger.dataset.confirmLabel || "Thử lại";
            }
            return;
        }

        const form = document.createElement("form");
        form.method = "post";
        form.action = actionUrl;
        Object.entries(fields).forEach(([name, value]) => {
            if (!value) return;
            const input = document.createElement("input");
            input.type = "hidden";
            input.name = name;
            input.value = value;
            form.append(input);
        });
        document.body.append(form);
        form.submit();
    }

    function enhanceMobileTables(root) {
        if (!mobileTableQuery.matches) return;
        root.querySelectorAll("table.table:not([data-mobile-cards='off'])").forEach((table) => {
            if (table.dataset.mobileReady === "true") return;
            const headers = Array.from(table.querySelectorAll("thead th")).map((cell) => cell.textContent.trim());
            table.querySelectorAll("tbody tr").forEach((row) => {
                const cells = Array.from(row.children);
                if (cells.some((cell) => cell.hasAttribute("colspan"))) {
                    row.classList.add("mobile-empty-row");
                    return;
                }
                cells.forEach((cell, index) => {
                    cell.dataset.label = headers[index] || "";
                });
            });
            table.dataset.mobileReady = "true";
            table.closest(".table-responsive")?.classList.add("mobile-card-wrapper");
        });
    }

    function storageGet(key) {
        try { return window.localStorage.getItem(key); } catch (error) { return null; }
    }

    function storageSet(key, value) {
        try { window.localStorage.setItem(key, value); } catch (error) { /* Private mode can disable storage. */ }
    }

    function preferredTheme() {
        const saved = storageGet(themeKey);
        if (saved === "light" || saved === "dark") return saved;
        return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }

    function applyTheme(theme) {
        document.documentElement.dataset.theme = theme;
        document.documentElement.setAttribute("data-bs-theme", theme);
        storageSet(themeKey, theme);
        themeToggles.forEach((button) => {
            const next = theme === "dark" ? "sáng" : "tối";
            button.setAttribute("aria-label", `Chuyển sang giao diện ${next}`);
            button.setAttribute("title", `Chuyển sang giao diện ${next}`);
        });
    }

    function updateSidebarLabel() {
        if (!sidebarToggle) return;
        const expanded = desktopQuery.matches ? !body.classList.contains("sidebar-mini") : body.classList.contains("sidebar-open");
        sidebarToggle.setAttribute("aria-expanded", String(expanded));
        sidebarToggle.setAttribute("aria-label", expanded ? "Thu gọn menu" : "Mở menu");
    }

    function closeMobileSidebar() {
        body.classList.remove("sidebar-open");
        updateSidebarLabel();
    }

    applyTheme(preferredTheme());
    enhanceMobileTables(document);
    updateTopbar();
    if (liveClock) window.setInterval(updateTopbar, 30000);

    document.addEventListener("keydown", (event) => {
        if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;
        if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName)) return;
        const search = document.querySelector("input[type='search'], input[name='q']");
        if (!search) return;
        event.preventDefault();
        search.focus();
        search.select?.();
    });

    document.addEventListener("submit", (event) => {
        if (event.defaultPrevented) return;
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || !form.checkValidity()) return;
        if (form.dataset.submitting === "true") {
            event.preventDefault();
            return;
        }
        const submitter = event.submitter;
        if (!(submitter instanceof HTMLButtonElement) && !(submitter instanceof HTMLInputElement)) return;
        form.dataset.submitting = "true";
        submitter.classList.add("is-submitting");
        submitter.setAttribute("aria-disabled", "true");
        if (submitter instanceof HTMLButtonElement && submitter.textContent.trim()) {
            submitter.dataset.originalLabel = submitter.textContent;
            submitter.textContent = "Đang xử lý…";
        }
    });

    document.addEventListener("click", (event) => {
        const trigger = event.target.closest("[data-confirm-action]");
        if (!trigger) return;
        event.preventDefault();
        openActionDialog(trigger);
    });
    actionDialog?.querySelector("[data-dialog-cancel]")?.addEventListener("click", closeActionDialog);
    actionDialog?.querySelector("[data-dialog-confirm]")?.addEventListener("click", submitPendingAction);
    actionDialog?.addEventListener("cancel", (event) => { event.preventDefault(); closeActionDialog(); });

    const contentRoot = document.querySelector(".admin-content");
    if (contentRoot) {
        const pendingRoots = new Set();
        let tableFrame = null;
        new MutationObserver((mutations) => {
            if (!mobileTableQuery.matches) return;
            mutations.forEach((mutation) => mutation.addedNodes.forEach((node) => {
                if (node.nodeType !== Node.ELEMENT_NODE) return;
                const table = node.closest("table.table");
                if (table) {
                    // A live refresh can insert rows into an existing table.
                    delete table.dataset.mobileReady;
                    pendingRoots.add(table.parentElement);
                } else if (node.querySelector("table.table")) {
                    pendingRoots.add(node);
                }
            }));
            if (!pendingRoots.size || tableFrame !== null) return;
            tableFrame = window.requestAnimationFrame(() => {
                tableFrame = null;
                pendingRoots.forEach((root) => {
                    if (root.isConnected) enhanceMobileTables(root);
                });
                pendingRoots.clear();
            });
        }).observe(contentRoot, {childList: true, subtree: true});
    }
    const enhanceAfterResize = () => enhanceMobileTables(document);
    if (mobileTableQuery.addEventListener) mobileTableQuery.addEventListener("change", enhanceAfterResize);
    else mobileTableQuery.addListener(enhanceAfterResize);

    themeToggles.forEach((button) => {
        button.addEventListener("click", () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
    });

    if (sidebarToggle) {
        if (desktopQuery.matches && storageGet(sidebarKey) === "true") body.classList.add("sidebar-mini");

        sidebarToggle.addEventListener("click", () => {
            if (desktopQuery.matches) {
                body.classList.toggle("sidebar-mini");
                storageSet(sidebarKey, String(body.classList.contains("sidebar-mini")));
            } else {
                body.classList.toggle("sidebar-open");
            }
            updateSidebarLabel();
        });

        sidebarClosers.forEach((item) => item.addEventListener("click", closeMobileSidebar));
        sidebarLinks.forEach((item) => item.addEventListener("click", () => {
            if (!desktopQuery.matches) closeMobileSidebar();
        }));
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && body.classList.contains("sidebar-open")) closeMobileSidebar();
        });

        const handleBreakpoint = () => {
            body.classList.remove("sidebar-open");
            body.classList.toggle("sidebar-mini", desktopQuery.matches && storageGet(sidebarKey) === "true");
            updateSidebarLabel();
        };
        if (desktopQuery.addEventListener) desktopQuery.addEventListener("change", handleBreakpoint);
        else desktopQuery.addListener(handleBreakpoint);
        updateSidebarLabel();
    }
})();
