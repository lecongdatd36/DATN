var cqTranslate_home = window.gettext || (text => text);
document.addEventListener("DOMContentLoaded", () => {
    "use strict";
    const root = document.querySelector("[data-cq-home]");
    if (!root) return;
    const cards = [...root.querySelectorAll("[data-cq-dish]")];
    const filters = [...root.querySelectorAll("[data-cq-category]")];
    const more = root.querySelector("[data-cq-show-more]");
    const empty = root.querySelector("[data-cq-empty]");
    const label = root.querySelector("[data-cq-menu-label]");
    let category = "all";
    let expanded = false;

    function renderDishes() {
        const matched = cards.filter(card => category === "all" || card.dataset.category === category);
        const visible = new Set(expanded || category !== "all" ? matched : matched.slice(0, 4));
        cards.forEach(card => { card.hidden = !visible.has(card); });
        if (more) more.hidden = category !== "all" || expanded || matched.length <= 4;
        if (empty) empty.hidden = matched.length !== 0 || cards.length === 0;
        const selected = filters.find(button => button.dataset.cqCategory === category);
        const title = category === "all" ? cqTranslate_home("Món ngon cho bữa cơm nhà") : selected?.querySelector("span")?.textContent || cqTranslate_home("Thực đơn");
        if (label) label.textContent = `${title} · ${visible.size} ${cqTranslate_home('món')}`;
        filters.forEach(button => {
            const active = button.dataset.cqCategory === category;
            button.classList.toggle("is-active", active);
            button.setAttribute("aria-pressed", String(active));
        });
    }
    filters.forEach(button => button.addEventListener("click", () => {
        category = button.dataset.cqCategory;
        expanded = false;
        renderDishes();
    }));
    more?.addEventListener("click", () => { expanded = true; renderDishes(); });
    renderDishes();
});
