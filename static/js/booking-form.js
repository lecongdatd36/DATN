"use strict";

document.querySelectorAll("[data-booking-form]").forEach((form) => {
    const phone = form.elements.customer_phone;
    const name = form.elements.customer_name;
    const newCustomer = form.querySelector("[data-new-customer]");
    const customerResult = form.querySelector("[data-booking-customer-result]");
    const arrival = form.elements.starts_at;
    const party = form.elements.party_size;
    const duration = form.elements.duration_minutes;
    const table = form.elements.table;
    const tableResult = form.querySelector("[data-booking-tables-result]");
    const summary = form.querySelector("[data-booking-summary]");
    let customerName = "";
    let customerRequest = 0;
    let tableRequest = 0;
    let customerTimer;
    let tableTimer;
    let preferredTable = table.value;

    function updateSummary() {
        const tableLabel = table.value ? table.selectedOptions[0]?.textContent : "Chưa chọn bàn";
        const period = form.querySelector("[data-duration-preview]").textContent;
        summary.textContent = `${customerName || name.value || "Chưa xác định khách"} · ${phone.value || "Chưa nhập SĐT"} · ${party.value || "?"} khách · ${tableLabel}. ${period}`;
    }

    async function lookupCustomer() {
        const request = ++customerRequest;
        const value = phone.value.trim();
        if (!value) return;
        customerResult.textContent = "Đang tìm khách hàng…";
        try {
            const response = await fetch(`${form.dataset.customerUrl}?${new URLSearchParams({phone: value})}`, {headers: {Accept: "application/json"}});
            if (!response.ok) throw new Error("Không tra được khách hàng. Kiểm tra số điện thoại và thử lại.");
            const data = await response.json();
            if (request !== customerRequest) return;
            customerName = data.found ? data.name : "";
            newCustomer.hidden = data.found;
            name.required = !data.found && form.dataset.canAddCustomer === "true";
            customerResult.textContent = data.found ? `Khách hàng: ${data.name}` : (form.dataset.canAddCustomer === "true" ? "Khách mới. Nhập tên bên dưới để tạo hồ sơ cùng lịch đặt." : "Chưa có hồ sơ. Nhờ nhân viên có quyền thêm khách hàng trước khi đặt bàn.");
            updateSummary();
        } catch (error) {
            if (request !== customerRequest) return;
            customerResult.textContent = error.message;
        }
    }

    async function loadTables() {
        const request = ++tableRequest;
        if (!arrival.value || !party.value) {
            table.replaceChildren(new Option("Chọn giờ đến và số khách trước", ""));
            tableResult.textContent = "Chọn giờ đến và số khách để tìm bàn phù hợp.";
            updateSummary();
            return;
        }
        tableResult.textContent = "Đang tìm bàn phù hợp…";
        const params = new URLSearchParams({starts_at: arrival.value, party_size: party.value, duration_minutes: duration.value, booking_id: form.dataset.bookingId});
        try {
            const response = await fetch(`${form.dataset.tablesUrl}?${params}`, {headers: {Accept: "application/json"}});
            if (request !== tableRequest) return;
            if (!response.ok) {
                table.replaceChildren(new Option("Vui lòng kiểm tra thời gian và số khách", ""));
                tableResult.textContent = "Chưa tìm được bàn. Kiểm tra giờ phục vụ, số khách và thời lượng.";
                updateSummary();
                return;
            }
            const data = await response.json();
            if (request !== tableRequest) return;
            table.replaceChildren(new Option(data.tables.length ? "Chọn bàn phù hợp" : "Không còn bàn phù hợp", ""));
            for (const row of data.tables) table.add(new Option(row.label, String(row.id)));
            if (data.tables.some(row => String(row.id) === preferredTable)) table.value = preferredTable;
            tableResult.textContent = data.tables.length ? `Có ${data.tables.length} bàn phù hợp. Bàn được kiểm tra lại khi lưu.` : "Hết bàn phù hợp. Thử đổi giờ đến hoặc số khách.";
            updateSummary();
        } catch {
            if (request !== tableRequest) return;
            tableResult.textContent = "Không tải được danh sách bàn. Vui lòng thử lại.";
        }
    }

    phone.addEventListener("input", () => {
        clearTimeout(customerTimer);
        ++customerRequest;
        customerName = "";
        name.value = "";
        name.required = false;
        newCustomer.hidden = true;
        customerResult.textContent = "Nhập số điện thoại để kiểm tra tên khách hàng.";
        if (phone.value.replace(/\D/g, "").length >= 10) customerTimer = setTimeout(lookupCustomer, 350);
        updateSummary();
    });
    phone.addEventListener("change", lookupCustomer);
    for (const field of [arrival, party, duration]) field.addEventListener("input", () => {
        clearTimeout(tableTimer);
        ++tableRequest;
        table.replaceChildren(new Option("Đang cập nhật bàn phù hợp…", ""));
        updateSummary();
        tableTimer = setTimeout(loadTables, 250);
    });
    table.addEventListener("change", () => { preferredTable = table.value; updateSummary(); });
    name.addEventListener("input", updateSummary);
    newCustomer.hidden = !name.value;
    if (phone.value) lookupCustomer();
    loadTables();
    updateSummary();
});
