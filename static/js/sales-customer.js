document.addEventListener("DOMContentLoaded", () => {
  const workspace = document.querySelector("[data-customer-lookup-url]");
  if (!workspace) return;
  const lookupUrl = workspace.dataset.customerLookupUrl;

  document.querySelectorAll("[data-customer-lookup-form]").forEach((form) => {
    const phoneInput = form.querySelector("[data-customer-phone]");
    const searchButton = form.querySelector("[data-customer-search]");
    const result = form.querySelector("[data-customer-result]");
    const newCustomer = form.querySelector("[data-new-customer]");
    const nameInput = form.querySelector("[name='customer_name']");
    const modeButtons = [...form.querySelectorAll("[data-customer-mode-button]")];
    let timer;
    let controller;

    const showNewCustomer = (show) => {
      newCustomer.hidden = !show;
      nameInput.required = show && Boolean(phoneInput.value.trim());
      if (!show) nameInput.value = "";
    };

    const setMode = (mode) => {
      form.dataset.customerMode = mode;
      modeButtons.forEach((button) => button.classList.toggle("active", button.dataset.customerModeButton === mode));
      showNewCustomer(mode === "new");
      if (mode === "existing") window.setTimeout(() => phoneInput.focus(), 0);
    };

    const reset = () => {
      showNewCustomer(form.dataset.customerMode === "new");
      result.className = "customer-lookup-result small my-2 text-secondary";
      result.textContent = "Dùng số điện thoại để lưu lịch sử và tích điểm.";
    };

    const lookup = async () => {
      const phone = phoneInput.value.trim();
      if (!phone) return reset();
      controller?.abort();
      controller = new AbortController();
      result.className = "customer-lookup-result small my-2 text-secondary";
      result.textContent = "Đang tìm khách hàng…";
      try {
        const response = await fetch(`${lookupUrl}?phone=${encodeURIComponent(phone)}`, {
          headers: { "X-Requested-With": "XMLHttpRequest" },
          signal: controller.signal,
        });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || "Số điện thoại không hợp lệ.");
        phoneInput.value = data.found ? data.customer.phone : data.phone;
        if (data.found) {
          showNewCustomer(false);
          const spending = new Intl.NumberFormat("vi-VN").format(Number(data.customer.total_spending));
          result.className = "customer-lookup-result small my-2 alert alert-success py-2";
          result.textContent = `${data.customer.name} · Hạng ${data.customer.tier} · Giảm ${data.customer.discount_percent}% · Đã chi ${spending}đ`;
        } else {
          setMode("new");
          showNewCustomer(true);
          result.className = "customer-lookup-result small my-2 alert alert-warning py-2";
          result.textContent = "Khách mới. Nhập tên; hệ thống sẽ tự tạo hồ sơ khi mở bàn.";
          nameInput.focus();
        }
      } catch (error) {
        if (error.name === "AbortError") return;
        showNewCustomer(false);
        result.className = "customer-lookup-result small my-2 alert alert-danger py-2";
        result.textContent = error.message;
      }
    };

    phoneInput.addEventListener("input", () => {
      clearTimeout(timer);
      nameInput.required = !newCustomer.hidden && Boolean(phoneInput.value.trim());
      if (!phoneInput.value.trim()) return reset();
      const digitCount = phoneInput.value.replace(/\D/g, "").length;
      if (digitCount >= 10) timer = setTimeout(lookup, 450);
    });
    searchButton.addEventListener("click", lookup);
    form.addEventListener("reset", reset);
    modeButtons.forEach((button) => button.addEventListener("click", () => setMode(button.dataset.customerModeButton)));
    setMode(form.dataset.customerMode || "new");
  });
});
