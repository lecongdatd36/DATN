"use strict";

document.querySelectorAll("[data-duration-preview]").forEach((preview) => {
    const form = preview.closest("form");
    const arrival = form.querySelector('[name="starts_at"]');
    const duration = form.querySelector('[name="duration_minutes"]');
    const formatter = new Intl.DateTimeFormat("vi-VN", {
        timeZone: "Asia/Ho_Chi_Minh", day: "2-digit", month: "2-digit", year: "numeric",
        hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    });
    function update() {
        const minutes = Number(duration.value || preview.dataset.defaultMinutes);
        if (!Number.isInteger(minutes) || minutes < 1 || minutes > 1440) {
            preview.textContent = "Nhập thời lượng từ 1 đến 1440 phút.";
            return;
        }
        // datetime-local represents restaurant time, regardless of the device timezone.
        const start = new Date(`${arrival.value}+07:00`);
        if (!arrival.value || Number.isNaN(start.getTime())) {
            preview.textContent = `Thời lượng dự kiến: ${minutes} phút. Chọn giờ đến để xem khoảng giờ.`;
            return;
        }
        const end = new Date(start.getTime() + minutes * 60000);
        preview.textContent = `Dự kiến dùng bàn: ${formatter.format(start)} – ${formatter.format(end)} (${minutes} phút).`;
    }
    arrival.addEventListener("input", update);
    duration.addEventListener("input", update);
    update();
});
