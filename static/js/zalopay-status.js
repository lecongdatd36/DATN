var cqTranslate_zalopay_status = window.gettext || (text => text);
(() => {
  const root = document.querySelector('[data-zalopay-result]');
  if (!root) return;
  const form = root.querySelector('[data-query-payment]');
  const button = form.querySelector('button');
  const message = root.querySelector('[data-payment-message]');
  const gateway = root.querySelector('[data-open-gateway]');
  const terminal = () => ['PAID', 'REVIEW', 'FAILED', 'ABANDONED'].includes(root.dataset.status);
  const canPoll = () => !terminal() && root.dataset.autoPoll !== 'false';
  let busy = false;
  const idleLabel = button.textContent;
  const labels = {
    PAID: cqTranslate_zalopay_status('Máy chủ đã xác minh thanh toán thành công.'),
    REVIEW: cqTranslate_zalopay_status('Giao dịch đang được nhà hàng đối soát. Vui lòng giữ mã giao dịch để kiểm tra.'),
    FAILED: cqTranslate_zalopay_status('Giao dịch chưa thành công. Quay lại đơn để tạo yêu cầu mới.'),
    ABANDONED: cqTranslate_zalopay_status('Đã đổi phương thức thanh toán. Trở về bàn để chọn cách thanh toán khác.'),
    PENDING: cqTranslate_zalopay_status('Chưa xác minh được thanh toán. Giữ mã giao dịch và tiếp tục chờ hoặc truy vấn lại.')
  };
  async function refresh(query = false) {
    if (busy || document.hidden) return;
    busy = true;
    button.disabled = true;
    button.textContent = cqTranslate_zalopay_status('Đang kiểm tra…');
    root.setAttribute('aria-busy', 'true');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 25000);
    try {
      const response = await fetch(query ? root.dataset.queryUrl : root.dataset.stateUrl, {
        method: query ? 'POST' : 'GET', credentials: 'same-origin',
        cache: 'no-store', signal: controller.signal,
        headers: query ? {'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value, 'Accept': 'application/json'} : {'Accept': 'application/json'}
      });
      const state = await response.json();
      if (!response.ok) { message.textContent = state.error || cqTranslate_zalopay_status('Chưa lấy được kết quả.'); return; }
      root.dataset.status = state.status;
      root.dataset.autoPoll = String(state.auto_poll);
      root.querySelector('[data-payment-status]').textContent = state.status_label;
      message.textContent = state.status === 'PAID' ? labels.PAID : state.message || labels[state.status];
      message.classList.toggle('or-ok', state.status === 'PAID');
      root.querySelector('[data-payment-help]').hidden = !state.checkout_expired;
      root.querySelector('[data-payment-live-help]').hidden = Boolean(state.checkout_expired);
      const changeMethod = root.querySelector('[data-change-method-wrap]');
      if (changeMethod) changeMethod.hidden = !state.can_change_method;
      gateway.hidden = !state.order_url;
      if (state.order_url) gateway.href = state.order_url;
      if (state.return_url) {
        const target = new URL(state.return_url, location.origin);
        if (target.origin === location.origin) {
          root.querySelector('[data-payment-return]').href = target.href;
          if (state.status === 'PAID' && state.auto_return === true) location.replace(target.href);
        }
      }
    } catch (error) { message.textContent = error.name === 'AbortError'
      ? cqTranslate_zalopay_status('Máy chủ phản hồi quá chậm. Giữ mã giao dịch và kiểm tra lại; không thanh toán thêm.')
      : cqTranslate_zalopay_status('Chưa kết nối được máy chủ. Giữ mã giao dịch để kiểm tra lại.'); }
    finally { clearTimeout(timeout);busy = false;button.textContent = idleLabel;root.removeAttribute('aria-busy');button.disabled = ['PAID', 'REVIEW'].includes(root.dataset.status); }
  }
  form.addEventListener('submit', event => { event.preventDefault(); refresh(true); });
  setInterval(() => { if (canPoll()) refresh(); }, 5000);
  setInterval(() => { if (canPoll()) refresh(true); }, 30000);
  // A LAN/localhost callback cannot be reached by ZaloPay. Verify immediately
  // via the merchant server when the browser returns, never from redirect data.
  if (!['PAID', 'REVIEW', 'FAILED'].includes(root.dataset.status)) refresh(true);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && !terminal()) refresh(true); });
})();
