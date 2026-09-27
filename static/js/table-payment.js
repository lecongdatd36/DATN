(() => {
    "use strict";

    const root = document.querySelector("[data-table-payment]");
    if (!root) return;

    const checkboxes = Array.from(root.querySelectorAll("[data-payment-order]"));
    const count = root.querySelector("[data-selected-count]");
    const total = root.querySelector("[data-payment-total]");
    const submit = root.querySelector("[data-payment-submit]");
    const selectAll = root.querySelector("[data-select-all]");
    const money = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });

    const update = () => {
        const selected = checkboxes.filter((checkbox) => checkbox.checked);
        const amount = selected.reduce((sum, checkbox) => sum + Number(checkbox.dataset.amount || 0), 0);
        if (count) count.textContent = String(selected.length);
        if (total) total.textContent = `${money.format(amount)} đ`;
        if (submit) submit.disabled = selected.length === 0;
        if (selectAll) selectAll.textContent = selected.length === checkboxes.length ? "Bỏ chọn tất cả" : "Chọn tất cả";
    };

    checkboxes.forEach((checkbox) => checkbox.addEventListener("change", update));
    selectAll?.addEventListener("click", () => {
        const shouldSelect = !checkboxes.every((checkbox) => checkbox.checked);
        checkboxes.forEach((checkbox) => { checkbox.checked = shouldSelect; });
        update();
    });
    update();
})();
