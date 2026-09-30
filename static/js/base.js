"use strict";

(function () {
    const sidebarKey = "qlnh.sidebarMini";
    const themeKey = "qlnh.colorTheme";
    const desktopQuery = window.matchMedia("(min-width: 992px)");
    const mobileTableQuery = window.matchMedia("(max-width: 767.98px)");
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

    function submitPendingAction() {
        if (!pendingAction) return;
        const reason = actionDialog.querySelector("[data-dialog-reason]");
        const needsReason = pendingAction.dataset.confirmReason === "true";
        if (needsReason && !reason.value.trim()) {
            actionDialog.querySelector("[data-dialog-reason-error]").hidden = false;
            reason.focus();
            return;
        }
        const form = document.createElement("form");
        form.method = "post";
        form.action = pendingAction.dataset.actionUrl || pendingAction.getAttribute("href") || pendingAction.getAttribute("formaction");
        const fields = {
            csrfmiddlewaretoken: csrfToken(),
            expected_revision: pendingAction.dataset.revision || "",
            expected_status: pendingAction.dataset.status || "",
            reason: needsReason ? reason.value.trim() : (pendingAction.dataset.reason || ""),
        };
        Object.entries(fields).forEach(([name, value]) => {
            if (!value) return;
            const input = document.createElement("input");
            input.type = "hidden";
            input.name = name;
            input.value = value;
            form.append(input);
        });
        const confirmButton = actionDialog.querySelector("[data-dialog-confirm]");
        confirmButton.disabled = true;
        confirmButton.textContent = "Đang xử lý...";
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
        const button = event.target.closest("[data-payment-fraction]");
        if (!button) return;
        const panel = button.closest("[data-payment-split]");
        const amount = document.querySelector("#id_amount");
        const parts = Number(button.dataset.paymentFraction);
        const remaining = Number(panel?.dataset.remaining);
        if (!amount || !Number.isFinite(parts) || parts < 1 || !Number.isFinite(remaining)) return;
        amount.value = String(Math.floor(remaining / parts));
        amount.focus();
        amount.select?.();
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
        new MutationObserver((mutations) => {
            if (!mobileTableQuery.matches) return;
            mutations.forEach((mutation) => mutation.addedNodes.forEach((node) => {
                if (node.nodeType === Node.ELEMENT_NODE) enhanceMobileTables(node.matches?.("table") ? node.parentElement : node);
            }));
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
