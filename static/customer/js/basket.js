var cqTranslate_basket = window.gettext || (text => text);
(() => {
    'use strict';
    const root = document.querySelector('[data-storefront-cart]');
    if (!root) return;
    const dialog = root.querySelector('[data-basket-dialog]');
    const money = value => new Intl.NumberFormat(document.documentElement.lang === 'en' ? 'en-US' : 'vi-VN').format(value) + cqTranslate_basket('đ');
    const csrf = root.querySelector('[name=csrfmiddlewaretoken]').value;
    const notice = root.querySelector('[data-basket-message]');
    let timer, state = {items: [], count: 0, total: 0, valid: true}, pending = Promise.resolve();
    function announce(message, error = false) {
        clearTimeout(timer);
        notice.textContent = message;
        notice.classList.toggle('is-error', error);
        notice.hidden = false;
        timer = setTimeout(() => { notice.hidden = true; }, 4000);
    }
    async function request(payload) {
        const response = await fetch(root.dataset.cartUrl, {
            method: payload ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
            headers: payload ? {'Content-Type': 'application/json', 'X-CSRFToken': csrf} : {},
            body: payload ? JSON.stringify(payload) : undefined
        });
        if (!response.headers.get('content-type')?.includes('application/json')) throw Error(cqTranslate_basket('Không kết nối được giỏ món. Vui lòng tải lại trang.'));
        const data = await response.json();
        if (data.cart) { state = data.cart; render(); }
        if (!response.ok || data.error) throw Error(data.error || cqTranslate_basket('Chưa cập nhật được giỏ món.'));
        return data;
    }
    function change(payload, message) {
        pending = pending.then(() => request(payload)).then(() => { if (message) announce(message); })
            .catch(error => announce(error.message, true));
        return pending;
    }
    function render() {
        document.querySelectorAll('[data-basket-count]').forEach(node => { node.textContent = state.count; });
        root.querySelector('[data-basket-total]').textContent = money(state.total);
        root.querySelector('[data-basket-floating]').hidden = state.count === 0;
        root.querySelector('[data-basket-empty]').hidden = state.count > 0;
        root.querySelector('[data-basket-clear]').hidden = state.count === 0;
        const checkout = root.querySelector('[data-basket-checkout]');
        checkout.hidden = state.count === 0;
        checkout.setAttribute('aria-disabled', String(!state.valid));
        const error = root.querySelector('[data-basket-error]');
        error.textContent = (state.errors || []).join(' ');
        error.hidden = !error.textContent;
        const container = root.querySelector('[data-basket-items]');
        const focused = document.activeElement?.closest('[data-basket-key]');
        const focusKey = focused?.dataset.basketKey;
        const focusControl = document.activeElement?.dataset.basketPlus !== undefined ? '[data-basket-plus]' : '[data-basket-minus]';
        container.replaceChildren();
        state.items.forEach(item => {
            const row = root.querySelector('[data-basket-row-template]').content.firstElementChild.cloneNode(true);
            row.dataset.basketKey = `${item.kind}-${item.id}`;
            row.querySelector('img').src = item.image || root.dataset.placeholder;
            row.querySelector('[data-basket-kind]').textContent = item.kind === 'combo' ? cqTranslate_basket('COMBO TRỌN BỮA') : cqTranslate_basket('MÓN LẺ');
            row.querySelector('[data-basket-name]').textContent = item.name;
            row.querySelector('[data-basket-description]').textContent = item.description;
            row.querySelector('[data-basket-quantity]').textContent = item.quantity;
            row.querySelector('[data-basket-line-total]').textContent = money(item.total);
            const payload = {kind: item.kind, id: item.id};
            row.querySelector('[data-basket-minus]').onclick = () => change({...payload, action: 'decrease'});
            row.querySelector('[data-basket-plus]').onclick = () => change({...payload, action: 'add'});
            row.querySelector('[data-basket-plus]').disabled = !item.available;
            row.querySelector('[data-basket-remove]').onclick = () => change({...payload, action: 'remove'});
            container.append(row);
            if (focusKey === row.dataset.basketKey) row.querySelector(focusControl)?.focus();
        });
    }
    document.querySelectorAll('[data-basket-open]').forEach(button => button.addEventListener('click', () => {
        if (!dialog.open) dialog.showModal();
    }));
    function closeBasket() {
        document.body.classList.remove('cq-basket-is-open');
        dialog.close();
    }
    root.querySelectorAll('[data-basket-close]').forEach(button => button.addEventListener('click', closeBasket));
    dialog.addEventListener('click', event => { if (event.target === dialog && event.clientX < dialog.getBoundingClientRect().left) closeBasket(); });
    dialog.addEventListener('close', () => { document.body.classList.remove('cq-basket-is-open'); });
    document.querySelectorAll('[data-basket-open]').forEach(button => button.addEventListener('click', () => document.body.classList.add('cq-basket-is-open')));
    root.querySelector('[data-basket-clear]').addEventListener('click', () => change({action: 'clear'}));
    root.querySelector('[data-basket-checkout]').addEventListener('click', async event => {
        event.preventDefault();
        const href = event.currentTarget.href;
        await pending;
        if (!state.valid) announce(cqTranslate_basket('Vui lòng bỏ món/combo không còn phục vụ trước khi đặt bàn.'), true);
        else window.location.assign(href);
    });
    document.querySelectorAll('[data-quick-booking]').forEach(form => form.addEventListener('submit', async event => {
        event.preventDefault();
        await pending;
        form.submit();
    }));
    document.addEventListener('click', event => {
        const button = event.target.closest('[data-basket-add]');
        if (!button || button.disabled) return;
        change({action: 'add', kind: button.dataset.basketAdd, id: Number(button.dataset.itemId)}, cqTranslate_basket('Đã thêm vào giỏ món.'));
    });
    pending = request().catch(error => announce(error.message, true));
    window.addEventListener('pageshow', event => { if (event.persisted) pending = request().catch(error => announce(error.message, true)); });
})();
