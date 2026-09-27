(() => {
    "use strict";

    const root = document.querySelector("[data-order-menu]");
    if (!root) return;

    const workspace = root.querySelector("[data-existing-total]");
    const cards = Array.from(root.querySelectorAll("[data-dish-card]")).map((card) => ({
        card,
        checkbox: card.querySelector("[data-dish-check]"),
        quantity: card.querySelector("[data-quantity]"),
        searchText: "",
    }));
    const search = root.querySelector("[data-menu-search]");
    const category = root.querySelector("[data-menu-category]");
    const categoryButtons = Array.from(root.querySelectorAll("[data-category-button]"));
    const selectedLabels = root.querySelectorAll("[data-selected-count], [data-checkout-count]");
    const visibleLabel = root.querySelector("[data-visible-count]");
    const selectedSummary = root.querySelector("[data-selected-summary]");
    const selectedEmpty = root.querySelector("[data-selected-empty]");
    const selectedTotalLabel = root.querySelector("[data-selected-total]");
    const grandTotalLabel = root.querySelector("[data-grand-total]");
    const submit = root.querySelector("[data-add-selected]");
    const existingTotal = Number(workspace?.dataset.existingTotal || 0);
    const normalize = (value) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
    const money = new Intl.NumberFormat("vi-VN");

    cards.forEach((item) => { item.searchText = normalize(item.card.dataset.searchText || ""); });

    const syncCard = (item) => item.card.classList.toggle("is-selected", item.checkbox.checked);
    const renderSelection = () => {
        const selected = cards.filter((item) => item.checkbox.checked);
        const fragment = document.createDocumentFragment();
        let selectedTotal = 0;

        selected.forEach((item) => {
            const quantity = Math.max(1, Math.min(100, Number(item.quantity.value || 1)));
            const subtotal = Number(item.card.dataset.price || 0) * quantity;
            selectedTotal += subtotal;
            const line = document.createElement("div");
            line.className = "bill-line is-new";
            const copy = document.createElement("div");
            const name = document.createElement("strong");
            const detail = document.createElement("small");
            const price = document.createElement("b");
            const actions = document.createElement("div");
            const remove = document.createElement("button");
            name.textContent = item.card.dataset.name || "Món ăn";
            detail.textContent = `${quantity} × ${money.format(Number(item.card.dataset.price || 0))} đ`;
            price.textContent = `${money.format(subtotal)} đ`;
            actions.className = "bill-line-actions";
            remove.className = "bill-remove";
            remove.type = "button";
            remove.textContent = "×";
            remove.setAttribute("aria-label", `Bỏ chọn ${item.card.dataset.name || "món ăn"}`);
            remove.addEventListener("click", () => {
                item.checkbox.checked = false;
                syncCard(item);
                renderSelection();
            });
            copy.append(name, detail);
            actions.append(price, remove);
            line.append(copy, actions);
            fragment.append(line);
        });

        selectedSummary?.replaceChildren(fragment);
        if (selectedEmpty) selectedEmpty.hidden = selected.length > 0;
        selectedLabels.forEach((label) => { label.textContent = String(selected.length); });
        if (selectedTotalLabel) selectedTotalLabel.textContent = `${money.format(selectedTotal)} đ`;
        if (grandTotalLabel) grandTotalLabel.textContent = `${money.format(existingTotal + selectedTotal)} đ`;
        if (submit) submit.disabled = selected.length === 0;
    };

    const filterCards = () => {
        const term = normalize(search?.value || "");
        const categoryId = category?.value || "";
        let visible = 0;
        cards.forEach((item) => {
            const matchesText = !term || item.searchText.includes(term);
            const matchesCategory = !categoryId || item.card.dataset.category === categoryId;
            item.card.hidden = !(matchesText && matchesCategory);
            if (!item.card.hidden) visible += 1;
        });
        categoryButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.categoryButton === categoryId));
        if (visibleLabel) visibleLabel.textContent = String(visible);
    };

    cards.forEach((item) => {
        const note = item.card.querySelector("[data-dish-note]");
        item.checkbox.addEventListener("change", () => { syncCard(item); renderSelection(); });
        item.card.querySelector("[data-quantity-minus]")?.addEventListener("click", () => {
            item.checkbox.checked = true;
            item.quantity.value = String(Math.max(1, Number(item.quantity.value || 1) - 1));
            syncCard(item);
            renderSelection();
        });
        item.card.querySelector("[data-quantity-plus]")?.addEventListener("click", () => {
            item.checkbox.checked = true;
            item.quantity.value = String(Math.min(100, Number(item.quantity.value || 1) + 1));
            syncCard(item);
            renderSelection();
        });
        item.quantity.addEventListener("input", () => {
            item.checkbox.checked = true;
            syncCard(item);
            renderSelection();
        });
        note.addEventListener("focus", () => {
            item.checkbox.checked = true;
            syncCard(item);
            renderSelection();
        });
        syncCard(item);
    });

    categoryButtons.forEach((button) => button.addEventListener("click", () => {
        if (category) category.value = button.dataset.categoryButton || "";
        filterCards();
    }));
    let filterFrame;
    const scheduleFilter = () => {
        if (filterFrame) cancelAnimationFrame(filterFrame);
        filterFrame = requestAnimationFrame(filterCards);
    };
    search?.addEventListener("input", scheduleFilter);
    category?.addEventListener("change", filterCards);
    renderSelection();
    filterCards();
})();
