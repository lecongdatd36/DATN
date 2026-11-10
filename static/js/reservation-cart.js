(() => {
  const form = document.querySelector('[data-preorder-cart]');
  if (!form) return;
  const money = value => new Intl.NumberFormat('vi-VN').format(value) + 'đ';
  const products = [...form.querySelectorAll('[data-dish-id]')];
  const entries = new Map(products.map(product => {
    const id = product.dataset.dishId;
    return [id, {product, input: product.querySelector('input[type="number"]'),
      row: form.querySelector(`[data-cart-item="${id}"]`), price: Number(product.dataset.price)}];
  }));
  function update() {
    let count = 0, total = 0;
    for (const entry of entries.values()) {
      const quantity = Math.max(0, Math.min(100, Math.trunc(Number(entry.input.value) || 0)));
      entry.row.hidden = quantity === 0;
      entry.row.querySelector('[data-item-count]').textContent = quantity;
      entry.row.querySelector('[data-line-total]').textContent = money(quantity * entry.price);
      entry.product.classList.toggle('is-selected', quantity > 0);
      count += quantity;
      total += quantity * entry.price;
    }
    form.querySelector('[data-cart-total]').textContent = money(total);
    document.querySelectorAll('[data-cart-count]').forEach(node => { node.textContent = count; });
    form.querySelector('[data-cart-empty]').hidden = count > 0;
  }
  form.addEventListener('click', event => {
    const control = event.target.closest('[data-quantity-delta], [data-remove]');
    if (!control || control.disabled) return;
    const entry = entries.get(control.dataset.target || control.dataset.remove);
    if (!entry) return;
    entry.input.value = control.hasAttribute('data-remove') ? 0 : Math.max(0, Math.min(100,
      (Math.trunc(Number(entry.input.value)) || 0) + Number(control.dataset.quantityDelta)));
    if (control.hasAttribute('data-remove')) {
      entry.row.querySelector('input').value = '';
      entry.product.querySelector('button[data-quantity-delta="1"]').focus();
    }
    entry.input.dispatchEvent(new Event('input', {bubbles: true}));
  });
  form.addEventListener('input', event => {
    if (event.target.matches('input[type="number"]')) update();
  });
  const search = form.querySelector('[data-dish-search]');
  const category = form.querySelector('[data-dish-category]');
  const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/gi, 'd').toLowerCase();
  function filter() {
    let visible = 0;
    const query = normalize(search.value.trim());
    for (const product of products) {
      product.hidden = !normalize(product.dataset.name).includes(query) ||
        Boolean(category.value && product.dataset.category !== category.value);
      if (!product.hidden) visible++;
    }
    form.querySelector('[data-no-results]').hidden = visible > 0;
  }
  search.addEventListener('input', filter);
  category.addEventListener('change', filter);
  // Persist edits before using the step navigation, too.
  document.querySelectorAll('.or-steps a').forEach(link => {
    if (link.getAttribute('href') === location.pathname) return;
    link.addEventListener('click', event => {
      event.preventDefault();
      const target = link.getAttribute('href').includes('/dat-mon-truoc-khong/') ? 'choice' : 'back';
      form.requestSubmit(form.querySelector(`button[value="${target}"]`));
    });
  });
  window.addEventListener('pageshow', update);
  update();
  form.dataset.cartReady = 'true';
})();
