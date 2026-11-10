(() => {
  const root = document.querySelector('[data-zalopay-result]');
  if (!root) return;
  const form = root.querySelector('[data-query-payment]');
  const button = form.querySelector('button');
  const message = root.querySelector('[data-payment-message]');
  const gateway = root.querySelector('[data-open-gateway]');
  const terminal = () => ['PAID', 'REVIEW', 'FAILED'].includes(root.dataset.status);
  let busy = false;
  const labels = {
    PAID: 'Máy chủ đã xác minh thanh toán thành công.',
    REVIEW: 'Đã nhận tiền Sandbox, nhà hàng cần đối soát trước khi xác nhận đơn.',
    FAILED: 'Giao dịch chưa thành công. Quay lại đơn để tạo yêu cầu mới.',
    PENDING: 'Chưa xác minh được thanh toán. Giữ mã giao dịch và tiếp tục chờ hoặc truy vấn lại.'
  };
  async function refresh(query = false) {
    if (busy || document.hidden) return;
    busy = true;
    button.disabled = true;
    try {
      const response = await fetch(query ? root.dataset.queryUrl : root.dataset.stateUrl, {
        method: query ? 'POST' : 'GET', credentials: 'same-origin',
        headers: query ? {'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value, 'Accept': 'application/json'} : {'Accept': 'application/json'}
      });
      const state = await response.json();
      if (!response.ok) { message.textContent = state.error || 'Chưa lấy được kết quả.'; return; }
      root.dataset.status = state.status;
      root.querySelector('[data-payment-status]').textContent = state.status_label;
      message.textContent = state.message || labels[state.status];
      message.classList.toggle('or-ok', state.status === 'PAID');
      gateway.hidden = !state.order_url;
      if (state.order_url) gateway.href = state.order_url;
    } catch { message.textContent = 'Chưa kết nối được máy chủ. Giữ mã giao dịch để kiểm tra lại.'; }
    finally { busy = false; button.disabled = ['PAID', 'REVIEW'].includes(root.dataset.status); }
  }
  form.addEventListener('submit', event => { event.preventDefault(); refresh(true); });
  setInterval(() => { if (!terminal()) refresh(); }, 5000);
  setInterval(() => { if (!terminal()) refresh(true); }, 30000);
  // A LAN/localhost callback cannot be reached by ZaloPay. Verify immediately
  // via the merchant server when the browser returns, never from redirect data.
  if (!terminal()) refresh(true);
})();
