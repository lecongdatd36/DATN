document.addEventListener("DOMContentLoaded", () => {
    const root = document.querySelector("[data-qr-check-in]");
    if (!root) return;
    const form = root.querySelector("[data-qr-check-in-form]");
    const button = root.querySelector("[data-qr-check-in-submit]");
    const message = root.querySelector("[data-qr-check-in-message]");
    let submitting = false;

    const setMessage = (value, isError = false) => {
        if (!message) return;
        message.textContent = value;
        root.classList.toggle("has-error", isError);
    };

    const poll = async () => {
        try {
            const response = await fetch(root.dataset.stateUrl, {
                credentials: "same-origin",
                headers: { "Accept": "application/json" },
                cache: "no-store",
            });
            if (!response.ok) return;
            const state = await response.json();
            if (state.ready) {
                setMessage("Nhân viên đã nhận bàn. Đang mở chức năng gọi món...");
                window.location.replace(state.refresh_url);
                return;
            }
            if (!state.request) return;
            if (state.request.status === "WAITING_CONFIRMATION") {
                setMessage(`Yêu cầu ${state.request.code} đang chờ nhân viên xác nhận. Trang sẽ tự mở gọi món sau khi bàn được nhận.`);
                if (form) form.hidden = true;
            } else if (state.request.status === "REJECTED") {
                setMessage(`Nhân viên đã từ chối: ${state.request.reject_reason || "Vui lòng liên hệ nhân viên."}`, true);
                if (form) {
                    form.hidden = false;
                    button.disabled = false;
                    button.textContent = "Yêu cầu nhận bàn";
                }
            } else if (state.request.status === "EXPIRED") {
                setMessage("Yêu cầu đã hết hạn. Bạn có thể gửi lại.", true);
                if (form) {
                    form.hidden = false;
                    button.disabled = false;
                    button.textContent = "Yêu cầu nhận bàn";
                }
            }
        } catch (_error) {
            // Mất mạng tạm thời: lần thăm dò tiếp theo sẽ thử lại.
        }
    };

    form?.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (submitting) return;
        const guestCount = Number(form.elements.guest_count.value);
        submitting = true;
        button.disabled = true;
        button.textContent = "Đang gửi...";
        setMessage("Đang gửi yêu cầu tới nhân viên...");
        try {
            const csrf = form.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
            const response = await fetch(root.dataset.requestUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrf,
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: JSON.stringify({ guest_count: guestCount }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || "Không thể gửi yêu cầu nhận bàn.");
            form.hidden = true;
            setMessage(`Yêu cầu ${data.request_code} đã được gửi. Trang sẽ tự mở gọi món sau khi nhân viên xác nhận.`);
            await poll();
        } catch (error) {
            setMessage(error.message || "Không thể gửi yêu cầu nhận bàn.", true);
            button.disabled = false;
            button.textContent = "Yêu cầu nhận bàn";
        } finally {
            submitting = false;
        }
    });

    poll();
    window.setInterval(poll, 3000);
});
