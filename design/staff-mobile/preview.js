"use strict";
(() => {
  const icons = {
    table: '<rect x="5" y="6" width="14" height="12" rx="3"/><path d="M8 3v3m8-3v3M8 18v3m8-3v3M2 9h3m-3 6h3m14-6h3m-3 6h3"/>',
    bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
    back: '<path d="m14 6-6 6 6 6"/>',
    search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    kitchen: '<path d="M8 18h8v3H8zM7 18v-5a5 5 0 0 1-4-5 4 4 0 0 1 5-4 5 5 0 0 1 8 0 4 4 0 0 1 5 4 5 5 0 0 1-4 5v5"/>',
    wifi: '<path d="M3 8a15 15 0 0 1 18 0M6 12a10 10 0 0 1 12 0m-9 4a5 5 0 0 1 6 0m-3 4h.01"/>',
    battery: '<rect x="2" y="6" width="17" height="12" rx="3"/><path d="M22 10v4M5 9h11v6H5z"/>'
  };
  const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.table}</svg>`;
  const escape = text => String(text).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const money = value => new Intl.NumberFormat('vi-VN').format(value) + 'đ';
  const dishes = [
    {id:1,name:'Nem hải sản',category:'Khai vị',price:89000,image:'assets/nem.webp'},
    {id:2,name:'Phở bò tái',category:'Món chính',price:75000,image:'assets/pho.webp'},
    {id:3,name:'Chè khúc bạch',category:'Tráng miệng',price:39000,image:'assets/che.webp'},
    {id:4,name:'Cà phê sữa đá',category:'Đồ uống',price:35000,image:'assets/caphe.webp'}
  ];
  const initialTables = [
    {code:'B01',state:'available',area:'Tầng 1',seats:4},
    {code:'B02',state:'occupied',area:'Tầng 1',seats:4,guests:3,total:320000},
    {code:'B03',state:'reserved',area:'Tầng 1',seats:6},
    {code:'B04',state:'occupied',area:'Tầng 1',seats:4,guests:4,total:303000},
    {code:'B05',state:'available',area:'Tầng 1',seats:2},
    {code:'B06',state:'cleaning',area:'Tầng 1',seats:4},
    {code:'B07',state:'available',area:'Sân vườn',seats:6},
    {code:'B08',state:'occupied',area:'Sân vườn',seats:4,guests:2,total:180000},
    {code:'B09',state:'available',area:'Sân vườn',seats:4}
  ];
  let tables, orders, selected, requests, bookings, qrRequests, metadata, online, failNext, history, customers, receipts, checkSequence;
  let role = 'service';
  const roleNames = {service:'Phục vụ',cashier:'Thu ngân',manager:'Quản lý'};
  const canCollect = () => role === 'cashier' || role === 'manager';
  const canManage = () => ['service','cashier','manager'].includes(role);
  const canAddCustomer = () => canManage() && document.querySelector('#demo-add-customer').checked;
  const phones = [...document.querySelectorAll('[data-phone]')];
  const settings = phones.map((phone, index) => ({screen:phone.dataset.screen,area:'Tầng 1',category:'Tất cả',query:'',sheet:null,index,toast:null}));
  const resetState = () => {
    tables = initialTables.map(table => ({...table}));
    selected = 'B04';
    orders = {B04:[{dishId:1,qty:1,status:'draft',note:'Ít cay'},{dishId:2,qty:1,status:'draft',note:''},{dishId:4,qty:2,status:'served',note:''}]};
    orders.B02 = [{dishId:2,qty:2,status:'ready',note:'Một tô không hành'},{dishId:4,qty:1,status:'served',note:''}];
    orders.B08 = [{dishId:1,qty:1,status:'served',note:''},{dishId:2,qty:2,status:'served',note:''}];
    requests = [{id:1,table:'B02',title:'Khách gọi phục vụ',detail:'Cần thêm chén và đũa · 2 phút trước'},{id:2,table:'B08',title:'Yêu cầu thanh toán',detail:'Khách muốn thanh toán tại bàn · 1 phút trước'}];
    customers=[{id:1,name:'Trần Thảo',phone:'0901234567',tier:'Vàng',discount:5,spending:6000000},{id:2,name:'Nguyễn Minh',phone:'0912344821',tier:'Thành viên',discount:2,spending:1500000},{id:3,name:'Lê Hoàng',phone:'0934567890',tier:'Thành viên',discount:0,spending:0}];
    bookings=[{id:1,code:'DB026',customerId:2,name:'Nguyễn Minh',phone:'0912344821',table:'B03',guests:5,time:'11:30',status:'confirmed',requestNote:'Sinh nhật · Có 1 trẻ em'}];
    qrRequests=[{id:11,type:'checkin',table:'B05',guests:2,title:'Nhận bàn qua QR',detail:'2 khách · Bàn trống · Vừa gửi'}, {id:12,type:'order',table:'B04',customerId:1,dishId:3,qty:2,note:'Ít ngọt',title:'Gọi món qua QR',detail:'2 chè khúc bạch · Ít ngọt'}];
    metadata={B02:{version:1,status:'open',splits:[],customerId:1,source:'walkin',note:'Khách cần phục vụ nhanh'},B04:{version:1,status:'open',splits:[],customerId:3,source:'walkin',note:'Có trẻ em · Ưu tiên lên món nhanh'}};online=true;failNext=false;history=[];
    receipts=[];checkSequence=0;
  };
  resetState();
  const order = () => orders[selected] || (orders[selected] = []);
  const dishById = id => dishes.find(dish => dish.id === Number(id));
  const total = items => items.filter(item=>item.status!=='cancelled').reduce((sum,item) => sum + dishById(item.dishId).price * item.qty,0);
  const count = items => items.filter(item=>item.status!=='cancelled').reduce((sum,item) => sum + item.qty,0);
  const table = () => tables.find(item => item.code === selected);
  const meta = (code=selected) => metadata[code] || (metadata[code]={version:1,status:'open',splits:[]});
  const customer = (code=selected) => customers.find(item=>item.id===meta(code).customerId)||null;
  const sourceLabel = (code=selected) => ({booking:'Khách đặt trước',qr:'Nhận bàn từ QR',walkin:'Khách đến trực tiếp'})[meta(code).source]||'Khách đến trực tiếp';
  const normalizedPhone = value => {
    let phone=String(value).replace(/[\s().-]/g,'');
    if(phone.startsWith('+84'))phone='0'+phone.slice(3);
    if(!/^0[0-9]{9,10}$/.test(phone))throw new Error('Nhập SĐT Việt Nam gồm 10–11 chữ số, bắt đầu bằng 0 hoặc dùng mã +84.');
    return phone;
  };
  const discountFor = (items,code=selected) => Math.round(total(items)*(customer(code)?.discount||0)/100);
  const checkItems = (code,checkId=null) => checkId===null?(orders[code]||[]):meta(code).splits.find(check=>check.id===checkId)?.items||[];
  const checkPaid = (code,checkId=null) => checkId===null?meta(code).status==='paid':Boolean(meta(code).splits.find(check=>check.id===checkId)?.paid);
  const eligibleCheckout = (code,checkId=null) => {
    const items=checkItems(code,checkId).filter(item=>item.status!=='cancelled');
    return tables.find(table=>table.code===code)?.state==='occupied'&&meta(code).status!=='cancelled'&&!checkPaid(code,checkId)&&items.length>0&&items.every(item=>item.status==='served');
  };
  const paymentQuote = (code,checkId=null,promotion=null) => {
    const items=checkItems(code,checkId),subtotal=total(items),memberDiscount=discountFor(items,code),eligible=subtotal-memberDiscount;
    const promotionDiscount=promotion?Math.min(eligible,50000,Math.round(eligible*.1)):0;
    return {subtotal,memberDiscount,promotionDiscount,promotionCode:promotion||'',due:Math.max(0,eligible-promotionDiscount),memberPercent:customer(code)?.discount||0};
  };
  const unpaidChecks = () => tables.filter(table=>table.state==='occupied').flatMap(table=>[
    ...(!checkPaid(table.code)&&checkItems(table.code).some(item=>item.status!=='cancelled')?[{code:table.code,checkId:null}]:[]),
    ...meta(table.code).splits.filter(check=>!check.paid).map(check=>({code:table.code,checkId:check.id}))
  ]);
  const liveItems = () => order().filter(item=>item.status!=='cancelled');
  const readyCount = () => Object.values(orders).flat().filter(item=>item.status==='ready').reduce((sum,item)=>sum+item.qty,0);
  const pendingCount = () => requests.length+qrRequests.length;
  const canRequestPayment = () => liveItems().length && liveItems().every(item=>item.status==='served') && meta().status==='open';
  const activeTotal = () => total(liveItems())-discountFor(liveItems());
  const tableTotal = code => (checkPaid(code)?0:paymentQuote(code).due) + meta(code).splits.filter(check=>!check.paid).reduce((sum,check)=>sum+paymentQuote(code,check.id).due,0);
  const guestContext = () => `<button class="guest-context" data-action="customer-info"><span class="guest-icon">${icon('user')}</span><span><strong>${escape(customer()?.name||'Khách vãng lai')}</strong><small>${customer()?`${customer().phone} · Hạng ${escape(customer().tier)}`:'Chưa liên kết hồ sơ khách hàng'} · ${table().guests||1} khách</small></span><span aria-hidden="true">›</span></button>`;
  const orderCustomerInfo = statusLabel => `${guestContext()}<div class="visit-meta"><span>${sourceLabel()} · Order #${selected}01</span><span class="pill">${statusLabel}</span></div>${meta().note?`<div class="visit-note"><strong>Ghi chú bàn</strong><p>${escape(meta().note)}</p></div>`:''}`;
  const billView = () => `<div class="bill"><div><span>${count(liveItems())} món · Tiền món</span><span>${money(total(liveItems()))}</span></div>${customer()?`<div><span>Thành viên ${escape(customer().tier)} · ${customer().discount}%</span><span>−${money(discountFor(liveItems()))}</span></div>`:'<div><span>Khách vãng lai</span><span>Chưa áp dụng ưu đãi</span></div>'}<div class="total"><span>Tạm tính</span><strong>${money(activeTotal())}</strong></div></div>`;
  const statusbar = () => `<div class="statusbar"><span>9:41</span><span>${icon('wifi')}${icon('battery')}</span></div>`;
  const indicator = '<div class="home-indicator" aria-hidden="true"></div>';
  const nav = screen => {
    const entries=canCollect()?[['tables','table','Bàn',0],['payments','check','Chờ thanh toán',unpaidChecks().filter(check=>eligibleCheckout(check.code,check.checkId)).length],['invoices','table','Hóa đơn',0],['personal','user','Cá nhân',0]]:[['tables','table','Bàn',0],['ready','kitchen','Mang món',readyCount()],['bookings','table','Đặt bàn',0],['requests','bell','Yêu cầu',pendingCount()]];
    return `<nav class="bottom-nav" aria-label="Điều hướng nhân viên">${entries.map(([key,image,label,badge])=>`<button data-action="go" data-screen="${key}" class="${screen===key?'active':''}" ${screen===key?'aria-current="page"':''}>${icon(image)}<span>${label}</span>${badge?`<b class="nav-count">${badge}</b>`:''}</button>`).join('')}</nav>`;
  };
  const header = title => `<header class="app-header"><div class="header-line"><div><p class="app-kicker">QLNH / ${roleNames[role].toUpperCase()}</p><h2>${title}</h2></div><button class="avatar" data-action="account" aria-label="Xem tài khoản nhân viên">MA</button></div><div class="shift"><i class="live-dot"></i>Ca sáng · 08:00 – 16:00</div></header>`;
  const orderHeader = title => `<header class="app-header"><div class="table-header"><button class="back" data-action="go" data-screen="tables" aria-label="Về sơ đồ bàn">${icon('back')}</button><div><h2>${title}</h2><small>Bàn ${selected} · ${table().area} · ${table().guests || 4} khách</small></div><button class="icon-button" data-action="table-info" aria-label="Thông tin bàn">${icon('more')}</button></div></header>`;
  const tableView = state => {
    const available = tables.filter(item => item.state==='available').length;
    const occupied = tables.filter(item => item.state==='occupied').length;
    return `${header('Sơ đồ bàn')}<div class="content">
      ${readyCount()?`<button class="task-banner ready-banner" data-action="go" data-screen="ready">${icon('kitchen')}<span><strong>${readyCount()} món sẵn sàng mang ra</strong><small>Bếp đã hoàn thành · Kiểm tra bàn và ghi chú</small></span><span>›</span></button>`:''}
      ${pendingCount()?`<button class="task-banner" data-action="go" data-screen="requests">${icon('bell')}<span><strong>${pendingCount()} yêu cầu cần xử lý</strong><small>Phục vụ, nhận bàn và gọi món QR</small></span><span>›</span></button>`:''}
      <div class="stats"><div class="stat"><strong>${available}</strong><small><i class="dot"></i>Bàn trống</small></div><div class="stat"><strong>${occupied}</strong><small><i class="dot busy"></i>Đang dùng</small></div><div class="stat"><strong>1</strong><small><i class="dot reserved"></i>Đã đặt</small></div></div>
      <div class="section-line"><h3>Chọn khu vực</h3><span>${tables.length} bàn</span></div><div class="chips">${['Tầng 1','Sân vườn','Tất cả'].map(area=>`<button class="chip ${state.area===area?'active':''}" data-action="area" data-value="${area}" aria-pressed="${state.area===area}">${area}</button>`).join('')}</div>
      <div class="tables">${tables.filter(item=>state.area==='Tất cả'||item.area===state.area).map(item=>{
        const labels={available:'Trống · Có thể nhận khách',occupied:`${item.guests} khách · ${money(tableTotal(item.code))}`,reserved:'Đã đặt · 11:30',cleaning:'Cần dọn bàn'};
        return `<button class="table-card ${item.state} ${item.code===selected?'selected':''}" data-action="table" data-code="${item.code}" aria-label="Bàn ${item.code}, ${labels[item.state]}"><div class="table-top"><strong>${item.code}</strong>${icon('table')}</div><p>${item.seats} chỗ · ${item.area}</p><small>${labels[item.state]}</small></button>`;
      }).join('')}</div></div>${nav('tables')}`;
  };
  const normalize = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[đĐ]/g,'d').toLowerCase();
  const dishList = state => {
    if(!canManage())return '<div class="empty">Tài khoản chưa có quyền gọi món.</div>';
    if(meta().status!=='open')return '<div class="empty">Order đang chờ thanh toán hoặc đã kết thúc.<br>Không thể gọi thêm món.</div>';
    const filtered=dishes.filter(dish=>(state.category==='Tất cả'||dish.category===state.category)&&normalize(dish.name).includes(normalize(state.query)));
    return filtered.map(dish=>{
      const qty=count(order().filter(item=>item.dishId===dish.id&&item.status==='draft'));
      return `<article class="dish"><img src="${dish.image}" alt="${dish.name}" width="68" height="68" decoding="async"><div class="dish-copy"><small>${dish.category}</small><h3>${dish.name}</h3><strong>${money(dish.price)}</strong><div><button class="dish-note" data-action="note" data-id="${dish.id}">＋ Ghi chú</button></div></div><div>${qty?`<span class="qty-label">Đã chọn ${qty}</span>`:''}<button class="add" data-action="add" data-id="${dish.id}" aria-label="Thêm ${dish.name}">＋</button></div></article>`;
    }).join('')||'<div class="empty">Không tìm thấy món phù hợp.<br>Thử tên món khác nhé.</div>';
  };
  const menuView = state => `${orderHeader('Gọi món')}<div class="context-strip"><span><i class="live-dot"></i> Đang phục vụ</span><strong>Order #${selected}01</strong></div>${guestContext()}<div class="menu-tools"><label class="search">${icon('search')}<input type="search" data-search placeholder="Tìm tên món…" value="${escape(state.query)}" aria-label="Tìm món"></label><div class="chips">${['Tất cả','Khai vị','Món chính','Tráng miệng','Đồ uống'].map(category=>`<button class="chip ${state.category===category?'active':''}" data-action="category" data-value="${category}" aria-pressed="${state.category===category}">${category}</button>`).join('')}</div></div><div class="content menu-list" data-menu-list>${dishList(state)}</div><div class="action-bar"><button class="primary cart-button" data-action="go" data-screen="order"><span><b class="cart-count">${count(order())}</b><span>Xem order<small>${count(order().filter(item=>item.status==='draft'))} món mới chưa gửi</small></span></span><span>${money(activeTotal())} ${icon('arrow')}</span></button></div>`;
  const itemView = (item,index) => {
    const dish=dishById(item.dishId);
    const labels={pending:'Chờ bếp nhận',cooking:'Đang chế biến',ready:'Chờ mang ra',served:'Đã phục vụ',cancelled:'Đã hủy'};
    const editable=canManage()&&meta().status==='open';
    const prepared=['cooking','ready','served'].includes(item.status);
    const cancellable=editable&&item.status!=='cancelled'&&(!prepared||role==='manager');
    return `<article class="order-item ${item.status==='cancelled'?'cancelled-item':''}"><img src="${dish.image}" alt="${dish.name}" width="51" height="51" decoding="async"><div class="order-item-copy"><h4>${dish.name}</h4><p>${escape(item.note||'Không có ghi chú')}</p>${item.status==='draft'&&editable?`<div class="stepper"><button data-action="minus" data-index="${index}" aria-label="Giảm ${dish.name}">−</button><span>${item.qty}</span><button data-action="plus" data-index="${index}" aria-label="Tăng ${dish.name}">＋</button></div>`:`<span class="pill ${['pending','cooking'].includes(item.status)?'cooking':''}">${item.qty} × ${labels[item.status]||'Món mới'}</span>`}${item.status==='ready'&&editable?`<button class="text-button" data-action="served" data-code="${selected}" data-index="${index}">✓ Đã mang ra</button>`:''}${cancellable?`<button class="danger-link" data-action="cancel-item" data-index="${index}">Hủy món</button>`:''}${item.status==='cancelled'?`<p class="cancel-reason">${escape(item.reason)}</p>`:''}</div><strong class="order-price">${money(dish.price*item.qty)}</strong></article>`;
  };
  const orderView = () => {
    if(meta().status==='paid')return `${orderHeader('Order đã thanh toán')}<div class="content">${orderCustomerInfo('Đã thanh toán')}<div class="paid-banner">${icon('check')} Hóa đơn gốc đã thu đủ tiền</div>${canCollect()?`<button class="operation-row" data-action="receipt" data-id="${meta().receiptId}">Xem hóa đơn đã thanh toán ›</button>`:''}${meta().splits.filter(check=>!check.paid).map(check=>canCollect()?`<button class="operation-row" data-action="checkout" data-code="${selected}" data-check="${check.id}">Hóa đơn tách #${check.id} · ${money(paymentQuote(selected,check.id).due)} ›</button>`:`<p class="field-hint">Hóa đơn tách #${check.id} · Chờ thu ngân xử lý</p>`).join('')}<p class="field-hint">${table().state==='cleaning'?'Bàn chuyển sang cần dọn.':'Bàn vẫn phục vụ vì còn hóa đơn chưa thanh toán.'}</p></div>${nav('tables')}`;
    const items=order(),drafts=items.filter(item=>item.status==='draft'),sent=items.filter(item=>item.status!=='draft');
    const payable=canRequestPayment(),locked=meta().status!=='open';
    const statusLabel={open:'Đang phục vụ',payment:'Chờ thu ngân',cancelled:'Đã hủy'}[meta().status];
    const action=drafts.length&&!locked&&canManage()?'confirm-send':canCollect()&&eligibleCheckout(selected)?'checkout':payable&&canManage()?'payment':'go';
    const actionLabel=action==='confirm-send'?`Gửi ${count(drafts)} món mới xuống bếp`:action==='checkout'?'Thanh toán':action==='payment'?'Yêu cầu thanh toán':'Về sơ đồ bàn';
    return `${orderHeader('Order của bàn')}<div class="content">${orderCustomerInfo(statusLabel)}<div class="section-line"><h3>Món mới <span class="pill draft">${count(drafts)}</span></h3>${!locked&&canManage()?'<button class="text-button" data-action="go" data-screen="menu">＋ Thêm món</button>':''}</div>${drafts.length?items.map((item,index)=>item.status==='draft'?itemView(item,index):'').join(''):'<div class="empty compact">Không có món mới chưa gửi.</div>'}${sent.length?`<div class="section-line sent-heading"><h3>Đã gửi bếp / Lịch sử</h3><span>${count(sent)} món</span></div>${items.map((item,index)=>item.status!=='draft'?itemView(item,index):'').join('')}`:''}${billView()}${meta().splits.length?`<button class="operation-row" data-action="split">${meta().splits.length+1} hóa đơn của bàn · Xem tách / ghép ›</button>`:''}<button class="operation-row" data-action="table-info">Thao tác bàn / hóa đơn ${icon('more')}</button></div><div class="action-bar"><p class="action-hint">${drafts.length?'Chỉ gửi các món mới. Món đã gửi được giữ nguyên.':payable?'Tất cả món đã phục vụ. Có thể yêu cầu thanh toán.':locked?'Order đã khóa gọi món. Thu ngân xử lý hóa đơn.':'Còn món chưa phục vụ xong. Theo dõi tại mục Mang món.'}</p><button class="primary" data-action="${action}" data-screen="tables">${icon(action==='confirm-send'?'kitchen':'check')}${actionLabel}</button></div>`;
  };
  const requestView = () => `${header('Yêu cầu phục vụ')}<div class="content"><div class="section-line"><h3>Đang chờ xử lý</h3><span>${pendingCount()} yêu cầu</span></div>${qrRequests.map(item=>`<article class="request-card"><div class="section-line"><span class="pill cooking">QR · Bàn ${item.table}</span><span>Vừa gửi</span></div><h3>${item.title}</h3><p>${item.detail}</p>${canManage()?`<div class="request-actions"><button class="primary" data-action="qr-review" data-id="${item.id}">Kiểm tra & xác nhận</button><button class="secondary-button" data-action="qr-reject" data-id="${item.id}">Từ chối</button></div>`:'<p>Nhân viên phục vụ tiếp nhận yêu cầu này.</p>'}</article>`).join('')}${requests.map(item=>`<article class="request-card"><span class="pill draft">Bàn ${item.table}</span><h3 style="margin-top:12px">${item.title}</h3><p>${item.detail}</p><button class="primary" data-action="request" data-id="${item.id}">${item.id===2?'Kiểm tra order trước khi thanh toán':'Đánh dấu đã xử lý'}</button></article>`).join('')||(!qrRequests.length?'<div class="empty">✓ Đã xử lý hết yêu cầu.<br>Bạn có thể tiếp tục phục vụ.</div>':'')}</div>${nav('requests')}`;
  const readyView = () => `${header('Món chờ mang ra')}<div class="content"><div class="section-line"><h3>Bếp đã hoàn thành</h3><span>${readyCount()} món</span></div>${Object.entries(orders).flatMap(([code,items])=>items.map((item,index)=>item.status==='ready'?`<article class="request-card ready-card"><div class="section-line"><strong>Bàn ${code}</strong><span class="pill">Sẵn sàng</span></div><div class="ready-dish"><img src="${dishById(item.dishId).image}" alt="${dishById(item.dishId).name}" width="64" height="64"><div><h3>${item.qty} × ${dishById(item.dishId).name}</h3><p class="important-note">${escape(item.note||'Không có ghi chú')}</p></div></div><p>Kiểm tra đúng bàn và số lượng trước khi xác nhận.</p>${canManage()?`<button class="primary" data-action="served" data-code="${code}" data-index="${index}">✓ Xác nhận đã mang ra</button>`:'<p>Nhân viên phục vụ xác nhận mang món.</p>'}</article>`:'')).join('')||'<div class="empty">Chưa có món chờ mang ra.<br>Món bếp làm xong sẽ xuất hiện ở đây.</div>'}</div>${nav('ready')}`;
  const bookingView = () => `${header('Lịch đặt bàn')}<div class="content"><div class="section-line"><h3>Lịch hôm nay</h3><span>${bookings.length} lượt khách</span></div>${bookings.map(item=>`<article class="request-card"><div class="section-line"><strong>${item.time} · Bàn ${item.table}</strong><span class="pill">${item.status==='confirmed'?'Đã xác nhận':'Đã nhận khách'}</span></div><h3>${escape(item.name)}</h3><p>${item.guests} khách · SĐT ${item.phone}<br>Mã đặt ${item.code}</p>${item.status==='confirmed'&&canManage()?`<button class="primary" data-action="booking-review" data-id="${item.id}">Đối chiếu & nhận khách</button>`:item.status==='seated'?`<button class="secondary-button" data-action="booking-order" data-code="${item.table}">Xem order</button>`:''}</article>`).join('')}</div>${nav('bookings')}`;
  const deniedView = () => `${header('Chưa có quyền')}<div class="content"><div class="empty">Tài khoản phục vụ chỉ gửi yêu cầu thanh toán.<br>Thu ngân hoặc quản lý phụ trách thu tiền.</div></div>${nav('tables')}`;
  const paymentsView = () => {
    if(!canCollect())return deniedView();
    const checks=unpaidChecks().sort((a,b)=>Number(eligibleCheckout(b.code,b.checkId))-Number(eligibleCheckout(a.code,a.checkId)));
    return `${header('Chờ thanh toán')}<div class="content"><div class="section-line"><h3>Hóa đơn chưa thu</h3><span>${checks.length} hóa đơn</span></div>${checks.map(check=>{
      const ready=eligibleCheckout(check.code,check.checkId),blocked=checkItems(check.code,check.checkId).filter(item=>!['served','cancelled'].includes(item.status));
      return `<article class="request-card"><div class="section-line"><strong>Bàn ${check.code}${check.checkId!==null?` · Tách #${check.checkId}`:''}</strong><span class="pill ${ready?'':'draft'}">${ready?'Có thể thu tiền':'Chưa đủ điều kiện'}</span></div><h3>${escape(customer(check.code)?.name||'Khách vãng lai')}</h3><p>${customer(check.code)?.phone||'Không liên kết hồ sơ'}<br>${count(checkItems(check.code,check.checkId))} món · ${money(paymentQuote(check.code,check.checkId).due)}</p>${blocked.length?`<p class="form-error">Còn ${count(blocked)} món chưa phục vụ: ${blocked.map(item=>escape(dishById(item.dishId).name)).join(', ')}</p>`:''}<button class="${ready?'primary':'secondary-button full-width'}" data-action="${ready?'checkout':'view-order'}" data-code="${check.code}" data-check="${check.checkId??''}">${ready?'Kiểm tra & thu tiền':'Xem món cần xử lý'}</button></article>`;
    }).join('')||'<div class="empty">Không có hóa đơn chờ thanh toán.</div>'}</div>${nav('payments')}`;
  };
  const checkoutQuoteView = quote => `<div class="bill"><div><span>Tiền món</span><span>${money(quote.subtotal)}</span></div><div><span>Ưu đãi thành viên · ${quote.memberPercent}%</span><span>−${money(quote.memberDiscount)}</span></div>${quote.promotionCode?`<div><span>Mã ${escape(quote.promotionCode)}</span><span>−${money(quote.promotionDiscount)}</span></div>`:''}<div class="total"><span>Cần thanh toán</span><strong>${money(quote.due)}</strong></div></div>`;
  const checkoutView = state => {
    if(!canCollect())return deniedView();
    const payment=state.checkout;
    if(!payment)return paymentsView();
    if(!eligibleCheckout(payment.code,payment.checkId))return `${orderHeader('Kiểm tra lại hóa đơn')}<div class="content"><p class="form-error">Hóa đơn chưa đủ điều kiện thu tiền hoặc đã được thanh toán. Kiểm tra các món chưa phục vụ trước khi tiếp tục.</p><button class="primary" data-action="go" data-screen="order">Xem order và trạng thái món</button></div>${nav('payments')}`;
    const quote=paymentQuote(payment.code,payment.checkId,payment.promo),items=checkItems(payment.code,payment.checkId).filter(item=>item.status!=='cancelled');
    const method=payment.values.payment_method||'CASH';
    return `${orderHeader('Thanh toán')}<div class="content checkout-content">
      <div class="checkout-customer"><span class="pill">${payment.checkId===null?'Hóa đơn gốc':`Hóa đơn tách #${payment.checkId}`}</span><h3>${escape(customer(payment.code)?.name||'Khách vãng lai')}</h3><p>${customer(payment.code)?.phone||'Không liên kết hồ sơ'} · Bàn ${payment.code}</p></div>
      <details class="checkout-items"><summary>Kiểm tra ${count(items)} món đã phục vụ</summary>${items.map(item=>`<div class="receipt-line"><span>${item.qty} × ${dishById(item.dishId).name}</span><strong>${money(dishById(item.dishId).price*item.qty)}</strong></div>`).join('')}</details>${checkoutQuoteView(quote)}
      <form data-form="checkout"><details class="promotion-details" ${payment.promo||payment.error?'open':''}><summary>Mã giảm giá ${payment.promo?`· ${escape(payment.promo)}`:'(nếu có)'}</summary><label class="sheet-label" for="promotion-${state.index}">Nhập mã</label><div class="phone-lookup"><input id="promotion-${state.index}" name="promotion_code" maxlength="30" placeholder="Nhập mã nếu có"><button type="button" data-action="apply-promotion">Áp dụng</button></div><p class="field-hint">Mã mẫu GIAM10: giảm 10% sau ưu đãi thành viên, tối đa 50.000đ; đơn từ 100.000đ.</p>${payment.error?`<p class="form-error" role="alert">${escape(payment.error)}</p>`:''}</details>
      <fieldset class="method-picker"><legend>Phương thức thanh toán</legend>${[['CASH','Tiền mặt'],['BANK_TRANSFER','Chuyển khoản']].map(([value,label])=>`<label class="${method===value?'active':''}"><input type="radio" name="payment_method" value="${value}" ${method===value?'checked':''}>${label}</label>`).join('')}</fieldset>
      ${method==='CASH'?`<label class="sheet-label" for="cash-${state.index}">Tiền khách đưa</label><input id="cash-${state.index}" name="cash_received" type="number" min="${quote.due}" step="1" inputmode="numeric" required placeholder="Nhập số tiền đã nhận"><div class="change-preview" aria-live="polite">Tiền thừa: <strong data-change>${money(Math.max(0,Number(payment.values.cash_received||0)-quote.due))}</strong></div>`:`<label class="sheet-label" for="reference-${state.index}">Mã giao dịch / tham chiếu (nếu có)</label><input id="reference-${state.index}" name="transaction_code" maxlength="100" placeholder="Nhập mã đối chiếu"><label class="check-label"><input name="received_transfer" type="checkbox" required> Đã kiểm tra và nhận đủ tiền vào tài khoản nhà hàng.</label>`}
      <button class="primary checkout-submit">Kiểm tra & xác nhận thu tiền</button></form><button class="secondary-button full-width" data-action="go" data-screen="order">Quay lại order / Tách hóa đơn</button></div>`;
  };
  const invoiceView = () => !canCollect()?deniedView():`${header('Hóa đơn đã thu')}<div class="content"><div class="section-line"><h3>Trong ca này</h3><span>${receipts.length} hóa đơn</span></div>${receipts.slice().reverse().map(receipt=>`<button class="invoice-card" data-action="receipt" data-id="${receipt.id}"><span><strong>${receipt.number} · Bàn ${receipt.code}</strong><small>${escape(receipt.customerName)} · ${receipt.methodLabel}</small></span><span><strong>${money(receipt.due)}</strong><small>Đã thanh toán ›</small></span></button>`).join('')||'<div class="empty">Chưa có hóa đơn được thanh toán trong ca.</div>'}</div>${nav('invoices')}`;
  const receiptView = state => {
    if(!canCollect())return deniedView();
    const receipt=receipts.find(receipt=>receipt.id===state.receiptId);
    if(!receipt)return invoiceView();
    return `${header('Thanh toán thành công')}<div class="content"><div class="paid-banner">${icon('check')} Đã thu đủ ${money(receipt.due)}</div><article class="receipt-paper"><div class="receipt-heading"><strong>QLNH</strong><span>HÓA ĐƠN MINH HỌA</span><small>${receipt.number} · Bàn ${receipt.code}${receipt.checkId!==null?` · Tách #${receipt.checkId}`:''}</small></div><p>${escape(receipt.customerName)}<br>${receipt.customerPhone||'Khách vãng lai'}<br>Thu ngân: ${escape(receipt.actor)} · ${receipt.time}</p>${receipt.items.map(item=>`<div class="receipt-line"><span>${item.qty} × ${dishById(item.dishId).name}</span><strong>${money(dishById(item.dishId).price*item.qty)}</strong></div>`).join('')}${checkoutQuoteView(receipt)}<p>${receipt.methodLabel}${receipt.reference?` · ${escape(receipt.reference)}`:''}</p>${receipt.method==='CASH'?`<div class="receipt-line"><span>Khách đưa / Tiền thừa</span><strong>${money(receipt.cashReceived)} / ${money(receipt.change)}</strong></div>`:''}</article><p class="field-hint">${tables.find(table=>table.code===receipt.code).state==='occupied'?'Bàn còn hóa đơn chưa thanh toán; tiếp tục phục vụ.':'Bàn đã chuyển sang cần dọn.'}</p><button class="primary" data-action="print-receipt" data-id="${receipt.id}">Xem / In hóa đơn</button><button class="secondary-button full-width" data-action="go" data-screen="payments">Tiếp tục thu tiền</button></div>${nav('invoices')}`;
  };
  const personalView = () => `${header('Cá nhân')}<div class="content"><div class="request-card"><h3>Minh Anh · ${roleNames[role]}</h3><p>Ca sáng · 08:00 – 16:00</p></div>${[['ready','Mang món'],['bookings','Đặt bàn'],['requests','Yêu cầu phục vụ']].map(([screen,label])=>`<button class="operation-row" data-action="go" data-screen="${screen}">${label} ›</button>`).join('')}<button class="operation-row" data-action="history">Lịch sử thao tác ›</button></div>${nav('personal')}`;
  const startCheckout = (state,code=selected,checkId=null) => {
    if(!canCollect()){openSheet(state,{type:'denied'});return;}
    if(!eligibleCheckout(code,checkId)){notify(state,'Chưa thể thu tiền: còn món chưa phục vụ, hóa đơn đã thu hoặc bàn không còn hoạt động.');return;}
    switchTable(code);state.checkout={code,checkId,version:meta(code).version,promo:null,values:{payment_method:'CASH'},error:''};
    go(state,'checkout');renderAll();
  };
  const recordReceipt = (code,checkId,quote,method,values={}) => {
    if(checkPaid(code,checkId))return null;
    const items=checkItems(code,checkId).filter(item=>item.status!=='cancelled').map(item=>({...item})),profile=customer(code);
    const receipt={...quote,id:receipts.length+1,number:'HDM-'+String(receipts.length+1).padStart(5,'0'),code,checkId,items,customerName:profile?.name||'Khách vãng lai',customerPhone:profile?.phone||'',method,methodLabel:{CASH:'Tiền mặt',BANK_TRANSFER:'Chuyển khoản'}[method],reference:String(values.transaction_code||''),cashReceived:Number(values.cash_received||0),change:method==='CASH'?Number(values.cash_received||0)-quote.due:0,actor:values.paymentActor||roleNames[role],time:new Date().toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'})};
    receipts.push(receipt);
    if(checkId===null){meta(code).status='paid';meta(code).receiptId=receipt.id;}
    else{const check=meta(code).splits.find(check=>check.id===checkId);check.paid=true;check.receiptId=receipt.id;}
    const stillOpen=meta(code).status!=='paid'||meta(code).splits.some(check=>!check.paid);
    tables.find(table=>table.code===code).state=stillOpen?'occupied':'cleaning';
    if(!stillOpen){requests=requests.filter(request=>request.table!==code);qrRequests=qrRequests.filter(request=>request.table!==code);bookings.filter(booking=>booking.table===code&&booking.status==='seated').forEach(booking=>{booking.status='completed';});}
    if(profile){profile.spending+=quote.due;if(profile.spending>=5000000){profile.tier='Vàng';profile.discount=5;}else if(profile.spending>=1000000){profile.tier='Thành viên';profile.discount=2;}}
    history.push({action:'Thu tiền '+receipt.number+' · '+money(receipt.due),code,actor:receipt.actor});
    return receipt;
  };
  const splitChecksView = () => meta().splits.map((check,index)=>`<div class="split-check"><strong>Hóa đơn tách #${check.id} · ${money(check.paid?receipts.find(receipt=>receipt.id===check.receiptId).due:paymentQuote(selected,check.id).due)}</strong><p>${check.items.map(item=>`${item.qty} × ${dishById(item.dishId).name}`).join('<br>')}</p>${check.paid?`<span class="pill">Đã thanh toán</span>${canCollect()?`<button class="secondary-button full-width" data-action="receipt" data-id="${check.receiptId}">Xem hóa đơn</button>`:''}`:canCollect()?`<button class="primary" data-action="checkout" data-code="${selected}" data-check="${check.id}">Thanh toán hóa đơn tách</button><button class="secondary-button full-width" data-action="merge" data-index="${index}">Ghép về hóa đơn gốc</button>`:''}</div>`).join('');
  const errorView = sheet => `<h3>${sheet.type==='offline'?'Chưa có kết nối mạng':sheet.type==='conflict'?'Order vừa được cập nhật':'Chưa gửi được thao tác'}</h3><p>${sheet.type==='offline'?'Dữ liệu đang hiển thị là lần xem trước. Các món mới vẫn được giữ trên màn hình, chưa gửi xuống bếp.':sheet.type==='conflict'?'Một nhân viên khác vừa cập nhật order. Hãy xem thông tin mới rồi xác nhận lại. Thao tác của bạn chưa được áp dụng.':'Chưa xác nhận thành công. Món và nội dung đã nhập được giữ lại. Vui lòng kiểm tra rồi thử lại.'}</p><button class="primary" data-action="restore-sheet">${sheet.type==='conflict'?'Xem dữ liệu mới':sheet.type==='offline'?'Quay lại kiểm tra':'Quay lại thử lại'}</button>`;
  const openSheet = (state,sheet) => {
    const code=sheet.code||selected;
    state.sheet={code,version:meta(code).version,...sheet};render(state.index);
    phones[state.index].querySelector('.sheet input,.sheet textarea,.sheet .primary,.sheet .secondary')?.focus({preventScroll:true});
  };
  const record = (action,reason='') => history.push({action,reason,code:selected,actor:roleNames[role]});
  const attempt = (state,callback,permission='manage',code=state.sheet?.code||selected) => {
    const saved=state.sheet?{...state.sheet}:null;
    if((permission==='manage'&&!canManage())||(permission==='collect'&&!canCollect())||(permission==='prepared'&&role!=='manager')){
      openSheet(state,{type:'denied'});return false;
    }
    if(!online){openSheet(state,{type:'offline',restore:saved});return false;}
    if(saved?.version!==undefined&&saved.version!==meta(code).version){openSheet(state,{type:'conflict',restore:saved});return false;}
    if(failNext){failNext=false;openSheet(state,{type:'failure',restore:saved});return false;}
    const current=meta(code);
    callback();current.version++;return true;
  };
  const receptionForm = state => {
    const sheet=state.sheet,target=tables.find(item=>item.code===sheet.code);
    const lookup=sheet.lookup,known=lookup?.found&&customers.find(item=>item.id===lookup.id);
    return `<h3>Nhận khách · Bàn ${target.code}</h3><p>${target.area} · Tối đa ${target.seats} khách${sheet.qrId?' · Từ yêu cầu QR':''}</p><form data-form="open"><fieldset class="customer-fields"><legend>Thông tin bàn</legend><label class="sheet-label" for="guests-${state.index}">Số khách <span aria-hidden="true">*</span></label><input id="guests-${state.index}" name="guests" type="number" min="1" max="${target.seats}" value="${sheet.qrId?qrRequests.find(item=>item.id===sheet.qrId)?.guests||2:2}" required></fieldset><fieldset class="customer-fields"><legend>Thông tin khách <span class="optional-label">Không bắt buộc</span></legend><label class="sheet-label" for="phone-${state.index}">Số điện thoại</label><div class="phone-lookup"><input id="phone-${state.index}" name="customer_phone" type="tel" inputmode="tel" autocomplete="tel" maxlength="24" placeholder="Nhập nếu khách cung cấp"><button type="button" data-action="lookup-customer">Tìm</button></div><div class="customer-result" aria-live="polite">${sheet.lookupError?`<p class="form-error">${escape(sheet.lookupError)}</p>`:known?`<div class="matched-customer"><strong>${escape(known.name)}</strong><span>${known.phone}</span><small>Hạng ${escape(known.tier)} · Ưu đãi ${known.discount}% · Đã chi ${money(known.spending)}</small><p>Đối chiếu với khách trước khi xác nhận mở bàn.</p></div>`:lookup&&!lookup.found?'<p class="field-hint">Chưa có hồ sơ với SĐT này. Nhập tên nếu khách muốn đăng ký.</p>':'<p class="field-hint">Có SĐT: tìm hồ sơ để đối chiếu. Để trống: tiếp tục phục vụ khách vãng lai.</p>'}</div>${lookup&&!lookup.found?`<div data-new-customer-fields><label class="sheet-label" for="name-${state.index}">Họ tên khách <span aria-hidden="true">*</span></label><input id="name-${state.index}" name="customer_name" autocomplete="name" maxlength="150" ${canAddCustomer()?'required':''} placeholder="Nhập họ tên khách">${!canAddCustomer()?'<p class="form-error">Tài khoản chưa có quyền thêm khách hàng. Nhờ người có quyền hỗ trợ, hoặc để trống SĐT nếu khách không đăng ký.</p>':'<p class="field-hint">Hồ sơ được tạo khi xác nhận mở bàn thành công.</p>'}</div>`:''}<button class="text-button clear-customer" type="button" data-action="clear-customer" ${sheet.values?.customer_phone?'':'hidden'}>Bỏ qua thông tin khách · Để trống SĐT</button></fieldset><fieldset class="customer-fields"><legend>Ghi chú phục vụ</legend><label class="sheet-label" for="visit-note-${state.index}">Ghi chú cho bàn</label><textarea id="visit-note-${state.index}" name="visit_note" rows="2" maxlength="1000" placeholder="Sinh nhật, có trẻ em, ưu tiên yên tĩnh…"></textarea><p class="field-hint">Yêu cầu chế biến nhập riêng ở từng món.</p></fieldset><button class="primary">Mở bàn và gọi món ${icon('arrow')}</button></form>`;
  };
  const sheetView = state => {
    if (!state.sheet) return '';
    const sheet=state.sheet;
    const field = name => escape(sheet.values?.[name]||'');
    let html='';
    if(sheet.type==='open') html=receptionForm(state);
    if(sheet.type==='note') html=`<h3>Ghi chú món</h3><p>${dishById(sheet.id).name} · ${money(dishById(sheet.id).price)}</p><form data-form="note"><label class="sheet-label" for="note-${state.index}">Yêu cầu chế biến cho món</label><textarea id="note-${state.index}" name="note" rows="3" maxlength="500" placeholder="Ví dụ: ít cay, không hành…"></textarea><button class="primary">Thêm món kèm ghi chú</button></form>`;
    if(sheet.type==='send') html=`<h3>Gửi món xuống bếp?</h3><p>Bàn ${selected} · ${count(order().filter(item=>item.status==='draft'))} món mới. Kiểm tra số lượng và ghi chú trước khi gửi.</p>${order().filter(item=>item.status==='draft').map(item=>`<div class="history-entry"><strong>${item.qty} × ${dishById(item.dishId).name}</strong>${item.note?`<p class="important-note">${escape(item.note)}</p>`:''}</div>`).join('')}<p>${count(order().filter(item=>item.status!=='draft'))} món đã gửi trước đó được giữ nguyên.</p><button class="primary" data-action="send">${icon('check')}Xác nhận gửi bếp</button>`;
    if(sheet.type==='account') html=`<h3>Minh Anh</h3><p>${roleNames[role]} · Ca sáng<br>08:00 – 16:00 · Khu vực Tầng 1</p><div class="order-context"><div><strong>Đang trong ca làm việc</strong><small>Tài khoản minh họa cho bản thiết kế</small></div><span class="pill">Hoạt động</span></div><button class="operation-row" data-action="history">Lịch sử thao tác ca này ›</button><p>${canCollect()?'Có quyền tách / ghép hóa đơn khi chờ thanh toán.':'Tách / ghép hóa đơn do thu ngân xử lý.'}</p>`;
    if(sheet.type==='customer-info') html=`<h3>Thông tin khách của bàn</h3><dl class="customer-details"><dt>Khách hàng</dt><dd>${escape(customer()?.name||'Khách vãng lai')}</dd><dt>Số điện thoại</dt><dd>${customer()?.phone||'Không cung cấp'}</dd><dt>Hồ sơ</dt><dd>${customer()?`KH${String(customer().id).padStart(6,'0')}`:'Không liên kết hồ sơ'}</dd><dt>Hạng thành viên</dt><dd>${customer()?`${escape(customer().tier)} · Ưu đãi ${customer().discount}%`:'Không áp dụng'}</dd><dt>Nguồn nhận khách</dt><dd>${sourceLabel()}</dd><dt>Bàn / Số khách</dt><dd>${selected} · ${table().guests||1} khách</dd><dt>Ghi chú bàn</dt><dd>${escape(meta().note||'Không có ghi chú')}${meta().booking?`<p>Mã đặt ${bookings.find(item=>item.id===meta().booking)?.code||''}</p>`:''}</dd></dl>${meta().source==='qr'&&!customer()?'<p>Yêu cầu QR nhận bàn không cung cấp tên hay số điện thoại của khách.</p>':''}`;
    if(sheet.type==='info') html=`<h3>Bàn ${selected}</h3><p>${table().area} · ${table().seats} chỗ · ${table().guests||4} khách<br>Order #${selected}01</p><button class="operation-row" data-action="go" data-screen="order">Xem order của bàn ›</button>${canManage()&&meta().status!=='cancelled'?'<button class="operation-row" data-action="move">Chuyển sang bàn trống ›</button>':''}${canCollect()?'<button class="operation-row" data-action="split">Tách / ghép hóa đơn ›</button>':'<p class="permission-note">Tách / ghép hóa đơn thuộc quyền thu ngân.</p>'}${canManage()&&meta().status==='open'?'<button class="operation-row danger-link" data-action="cancel-order">Hủy bàn / order ›</button>':''}<button class="operation-row" data-action="history">Lịch sử thao tác ›</button>`;
    if(sheet.type==='served'){
      const item=(orders[sheet.code]||[])[sheet.index];
      html=item?`<h3>Đã mang món ra bàn?</h3><p>Bàn ${sheet.code} · ${item.qty} × ${dishById(item.dishId).name}</p><p class="important-note">${escape(item.note||'Không có ghi chú')}</p><button class="primary" data-action="confirm-served">✓ Xác nhận đã phục vụ</button>`:'<h3>Món đã thay đổi</h3><p>Hãy kiểm tra lại danh sách.</p>';
    }
    if(sheet.type==='booking'){
      const booking=bookings.find(item=>item.id===sheet.id);
      const profile=customers.find(item=>item.id===booking.customerId);
      html=`<h3>Đối chiếu khách đặt bàn</h3><div class="matched-customer"><strong>${escape(booking.name)}</strong><span>${booking.phone}</span><small>${profile?`Hồ sơ ${escape(profile.name)} · Hạng ${escape(profile.tier)} · Ưu đãi ${profile.discount}%`:'Chưa có hồ sơ liên kết'}</small></div><p>Mã ${booking.code} · ${booking.time}<br>Bàn ${booking.table} · ${booking.guests} khách</p>${booking.requestNote?`<div class="visit-note"><strong>Yêu cầu khách đã gửi khi đặt</strong><p>${escape(booking.requestNote)}</p></div>`:''}<p>Giữ nguyên hồ sơ khách của lịch đặt khi mở order.</p><form data-form="booking"><label class="sheet-label" for="booking-note-${state.index}">Ghi chú phục vụ cho lượt khách</label><textarea id="booking-note-${state.index}" name="visit_note" rows="2" maxlength="1000">${escape(booking.requestNote||'')}</textarea><p class="field-hint">Đối chiếu và xác nhận lại yêu cầu của khách trước khi lưu vào order.</p><label class="check-label"><input name="verified" type="checkbox" required> Đã đối chiếu tên, số điện thoại và mã đặt với khách.</label><button class="primary">Nhận khách & mở order</button></form>`;
    }
    if(sheet.type==='qr'){
      const request=qrRequests.find(item=>item.id===sheet.id);
      html=request?`<h3>${request.title}</h3><p>Bàn ${request.table}<br>${escape(request.detail)}</p><p>${request.type==='order'?'Xác nhận sẽ thêm các món QR vào order và gửi bếp ngay. Các món mới bạn đang soạn không bị gửi kèm.':'QR chỉ gửi số khách, chưa có thông tin hồ sơ. Kiểm tra bàn còn trống và đối chiếu khách tại bàn.'}</p>${request.type==='order'?`<div class="matched-customer"><strong>Khách của order: ${escape(customer(request.table)?.name||'Khách vãng lai')}</strong><small>${customer(request.table)?.phone||'Không liên kết hồ sơ'} · Giữ nguyên khách của order khi duyệt món QR</small></div>`:''}<button class="primary" data-action="confirm-qr">${request.type==='order'?'Xác nhận & gửi món QR xuống bếp':'Nhận bàn · Khách vãng lai'}</button>${request.type==='checkin'?'<button class="secondary-button full-width" data-action="qr-customer">Khách muốn đăng ký thông tin? Nhận bàn trực tiếp</button>':''}`:'<h3>Yêu cầu đã được xử lý</h3>';
    }
    if(['reject','cancel-item','cancel-order'].includes(sheet.type)){
      const item=sheet.type==='cancel-item'?order()[sheet.index]:null;
      const blocked=sheet.type==='cancel-order'&&liveItems().some(line=>line.status!=='draft');
      const prepared=item&&['cooking','ready','served'].includes(item.status);
      const denied=prepared&&role!=='manager';
      html=`<h3>${sheet.type==='reject'?'Từ chối yêu cầu QR':sheet.type==='cancel-order'?'Hủy bàn / order':'Hủy món'}</h3><p>${item?`${item.qty} × ${dishById(item.dishId).name} · Bàn ${selected}`:sheet.type==='cancel-order'?`Bàn ${selected} · Chỉ hủy khi mọi món còn ở trạng thái mới.`:'Khách sẽ nhận được lý do từ chối.'}</p>${blocked?'<p class="form-error">Order đã có món gửi bếp. Cần xử lý từng món theo quyền, không được hủy cả bàn.</p>':denied?'<p class="form-error">Món đã bắt đầu chế biến. Cần người có quyền hủy món đã làm; hãy liên hệ quản lý.</p>':`<form data-form="${sheet.type}"><label class="sheet-label" for="reason-${state.index}">Lý do <span aria-hidden="true">*</span></label><textarea id="reason-${state.index}" name="reason" rows="3" maxlength="500" required placeholder="Nhập lý do cụ thể…">${field('reason')}</textarea><button class="primary danger-button">Xác nhận ${sheet.type==='reject'?'từ chối':'hủy'}</button></form>`}`;
    }
    if(sheet.type==='move'){
      const targets=tables.filter(item=>item.state==='available'&&item.seats>=(table().guests||1));
      html=`<h3>Chuyển bàn ${selected}</h3><p>Chọn bàn trống đủ chỗ. Bàn cũ chuyển sang trạng thái cần dọn.</p>${meta().splits.length?'<p class="form-error">Hãy ghép các hóa đơn đã tách trước khi chuyển bàn.</p>':targets.length?`<form data-form="move"><label class="sheet-label" for="target-${state.index}">Bàn đích</label><select id="target-${state.index}" name="target" required>${targets.map(item=>`<option value="${item.code}">${item.code} · ${item.area} · ${item.seats} chỗ</option>`).join('')}</select><button class="primary">Xác nhận chuyển bàn</button></form>`:'<p>Chưa có bàn trống phù hợp.</p>'}`;
    }
    if(sheet.type==='payment') html=`<h3>Gửi yêu cầu thanh toán?</h3><p>Bàn ${selected} · ${money(activeTotal())}<br>Tất cả món đã phục vụ. Order sẽ khóa gọi thêm món sau khi gửi.</p><button class="primary" data-action="confirm-payment">Chuyển cho thu ngân</button>`;
    if(sheet.type==='checkout-confirm'){
      const payment=state.checkout,quote=paymentQuote(payment.code,payment.checkId,payment.promo),method=payment.values.payment_method;
      html=`<h3>Xác nhận thu tiền?</h3><p>Bàn ${payment.code} · ${escape(customer(payment.code)?.name||'Khách vãng lai')}<br>${{CASH:'Tiền mặt',BANK_TRANSFER:'Chuyển khoản'}[method]}</p>${checkoutQuoteView(quote)}${method==='CASH'?`<p>Khách đưa: <strong>${money(Number(payment.values.cash_received))}</strong><br>Trả lại: <strong>${money(Number(payment.values.cash_received)-quote.due)}</strong></p>`:'<p>Đã đối chiếu và xác nhận nhận đủ tiền vào tài khoản nhà hàng.</p>'}<button class="primary" data-action="confirm-collect">Xác nhận đã nhận đủ tiền</button>`;
    }
    if(sheet.type==='print'){
      const receipt=receipts.find(receipt=>receipt.id===sheet.id);
      html=receipt?`<h3>${receipt.number} · Bàn ${receipt.code}</h3><p>${escape(receipt.customerName)} · ${receipt.methodLabel}</p>${receipt.items.map(item=>`<div class="receipt-line"><span>${item.qty} × ${dishById(item.dishId).name}</span><strong>${money(dishById(item.dishId).price*item.qty)}</strong></div>`).join('')}${checkoutQuoteView(receipt)}<p>Hóa đơn minh họa · Đã thanh toán</p><button class="primary" data-action="browser-print" data-id="${receipt.id}">In hóa đơn</button>`:'<p>Không tìm thấy hóa đơn.</p>';
    }
    if(sheet.type==='split'){
          const allowed=canCollect()&&meta().status==='payment'&&liveItems().every(item=>item.status==='served');
      html=`<h3>Tách / ghép hóa đơn</h3><p>Bàn ${selected} · Hóa đơn gốc ${money(activeTotal())}</p>${!canCollect()?'<p class="form-error">Chức năng thuộc quyền thu ngân.</p>':!allowed?'<p class="form-error">Chỉ tách sau khi tất cả món đã phục vụ và order đang chờ thanh toán.</p>':`<p>Nhập số lượng chuyển sang hóa đơn riêng. Hóa đơn gốc phải còn ít nhất một món.</p><form data-form="split">${order().map((item,index)=>item.status==='served'?`<label class="split-row"><span>${dishById(item.dishId).name}<small>${money(dishById(item.dishId).price)} / món · Có ${item.qty}</small></span><input name="qty-${index}" aria-label="Tách ${dishById(item.dishId).name}" type="number" min="0" max="${item.qty}" value="0" required></label>`:'').join('')}<button class="primary">Tạo hóa đơn tách</button></form>`}${canCollect()&&meta().status==='open'&&eligibleCheckout(selected)?'<button class="primary" data-action="prepare-split">Chuyển chờ thanh toán & tách hóa đơn</button>':''}${splitChecksView()}`;
    }
    if(sheet.type==='merge') html=`<h3>Ghép hóa đơn tách?</h3><p>Chuyển toàn bộ món của hóa đơn tách về hóa đơn gốc cùng bàn. Tổng tiền của bàn được giữ nguyên.</p><button class="primary" data-action="confirm-merge">Xác nhận ghép hóa đơn</button>`;
    if(sheet.type==='cleaning') html=`<h3>Bàn ${sheet.code} cần dọn</h3><p>Chỉ xác nhận sau khi bàn đã được vệ sinh và sẵn sàng nhận khách.</p><button class="primary" data-action="finish-cleaning">Đã dọn xong · Trả bàn trống</button>`;
    if(sheet.type==='denied') html='<h3>Bạn chưa có quyền thao tác</h3><p>Liên hệ nhân viên phụ trách hoặc quản lý để xử lý.</p>';
    if(sheet.type==='history') html=`<h3>Lịch sử thao tác</h3>${history.length?history.slice().reverse().map(entry=>`<div class="history-entry"><strong>${escape(entry.action)} · ${entry.code}</strong><p>${escape(entry.actor)}${entry.reason?`<br>Lý do: ${escape(entry.reason)}`:''}</p></div>`).join(''):'<p>Chưa có thao tác nào trong bản mẫu.</p>'}`;
    if(['offline','failure','conflict'].includes(sheet.type))html=errorView(sheet);
    return `<div class="overlay"><section class="sheet" role="dialog" aria-modal="true" aria-label="${({open:'Mở bàn',note:'Ghi chú món',send:'Xác nhận gửi bếp',account:'Tài khoản',info:'Thông tin bàn'})[sheet.type]||'Xác nhận thao tác'}">${html}<button class="secondary" data-action="close">${sheet.type==='send'?'Kiểm tra lại':'Đóng'}</button></section></div>`;
  };
  const render = (index, preserveScroll = true) => {
    const phone=phones[index],state=settings[index],top=preserveScroll?(phone.querySelector('.content')?.scrollTop||0):0;
    const views={tables:tableView,menu:menuView,order:orderView,requests:requestView,ready:readyView,bookings:bookingView,payments:paymentsView,checkout:checkoutView,invoices:invoiceView,receipt:receiptView,personal:personalView};
    phone.innerHTML=statusbar()+(!online?'<div class="connection-banner" role="status">Mất kết nối · Chưa thể gửi thay đổi</div>':'')+views[state.screen](state)+indicator+sheetView(state)+(state.toast?`<div class="toast" role="status">${escape(state.toast)}</div>`:'');
    const reception=phone.querySelector('[data-form="open"]');
    if(reception){
      const submit=reception.querySelector('button.primary'),fields=document.createElement('div'),actions=document.createElement('div');
      fields.className='reception-fields';actions.className='reception-actions';
      [...reception.children].filter(child=>child!==submit).forEach(child=>fields.append(child));
      actions.append(submit);reception.append(fields,actions);
    }
    const content=phone.querySelector('.content');if(content)content.scrollTop=top;
    phone.querySelectorAll('.statusbar,.app-header,.content,.bottom-nav,.action-bar,.menu-tools,.context-strip').forEach(element=>{element.inert=Boolean(state.sheet);});
    const saved=state.sheet?.values;
    if(saved)phone.querySelectorAll('.sheet form [name]').forEach(input=>{if(input.name in saved){if(input.type==='checkbox')input.checked=Boolean(saved[input.name]);else input.value=saved[input.name];}});
    const checkoutForm=phone.querySelector('[data-form="checkout"]');
    if(checkoutForm){
      checkoutForm.id='checkout-form-'+index;
      const submit=checkoutForm.querySelector('.checkout-submit'),bar=document.createElement('div');bar.className='action-bar';
      submit.setAttribute('form',checkoutForm.id);bar.append(submit);phone.querySelector('.home-indicator').before(bar);bar.inert=Boolean(state.sheet);
    }
    if(checkoutForm&&state.checkout)checkoutForm.querySelectorAll('[name]').forEach(input=>{
      if(!(input.name in state.checkout.values))return;
      if(input.type==='checkbox')input.checked=Boolean(state.checkout.values[input.name]);
      else if(input.type==='radio')input.checked=input.value===state.checkout.values[input.name];
      else input.value=state.checkout.values[input.name];
    });
  };
  const renderAll = () => phones.forEach((_,index)=>render(index));
  const go = (state,screen) => {state.screen=screen;state.sheet=null;render(state.index,false);};
  const notify = (state,text) => {state.toast=text;renderAll();window.clearTimeout(state.toastTimer);state.toastTimer=window.setTimeout(()=>{state.toast=null;render(state.index);},2600);};
  const add = (id,note='') => {let item=order().find(item=>item.dishId===id&&item.note===note&&item.status==='draft');if(item)item.qty++;else order().push({dishId:id,qty:1,note,status:'draft'});};
  const captureFields = (phone,state) => {
    const form=phone.querySelector('.sheet form');
    if(form&&state.sheet)state.sheet.values=Object.fromEntries(new FormData(form));
    const checkout=phone.querySelector('[data-form="checkout"]');
    if(checkout&&state.checkout)state.checkout.values=Object.fromEntries(new FormData(checkout));
  };
  const formError = (form,message) => {
    let error=form.querySelector('.form-error');
    if(!error){error=document.createElement('p');error.className='form-error';error.setAttribute('role','alert');form.prepend(error);}
    error.textContent=message;
  };
  const switchTable = code => {selected=code;settings.forEach(state=>{state.sheet=null;});};
  const complete = (state,callback,message,permission='manage',code=state.sheet?.code||selected) => {
    if(!attempt(state,callback,permission,code))return false;
    state.sheet=null;notify(state,message);return true;
  };
  phones.forEach((phone,index)=>{
    const state=settings[index];
    phone.addEventListener('click',event=>{
      const button=event.target.closest('[data-action]');if(!button)return;
      captureFields(phone,state);
      const action=button.dataset.action;
      if(action==='go'){go(state,button.dataset.screen);return;}
      if(action==='view-order'){switchTable(button.dataset.code);go(state,'order');renderAll();return;}
      if(action==='checkout'){
        startCheckout(state,button.dataset.code||selected,button.dataset.check?Number(button.dataset.check):null);return;
      }
      if(action==='apply-promotion'){
        if(!canCollect()||!state.checkout)return;
        const payment=state.checkout,code=String(payment.values.promotion_code||'').trim().toUpperCase();
        payment.error='';
        if(code&&(code!=='GIAM10'||total(checkItems(payment.code,payment.checkId))<100000))payment.error=code!=='GIAM10'?'Mã giảm giá không hợp lệ.':'Mã GIAM10 yêu cầu tiền món từ 100.000đ.';
        else{payment.promo=code||null;payment.values.promotion_code=code;}
        render(index);return;
      }
      if(action==='confirm-collect'){
        if(!state.checkout||state.sheet?.type!=='checkout-confirm')return;
        const payment=state.checkout,method=payment.values.payment_method;
        if(payment.version!==meta(payment.code).version){openSheet(state,{type:'conflict',restore:{type:'checkout-confirm',code:payment.code}});return;}
        if(!eligibleCheckout(payment.code,payment.checkId)){notify(state,'Hóa đơn đã thay đổi, đã thu tiền hoặc đang có giao dịch chờ. Hãy kiểm tra lại.');return;}
        const quote=paymentQuote(payment.code,payment.checkId,payment.promo);
        if(!['CASH','BANK_TRANSFER'].includes(method))return;
        if(method==='CASH'&&(!/^\d+$/.test(String(payment.values.cash_received||''))||Number(payment.values.cash_received)<quote.due)){notify(state,'Số tiền khách đưa chưa đủ hoặc không hợp lệ.');return;}
        if(method==='BANK_TRANSFER'&&!payment.values.received_transfer){notify(state,'Cần xác nhận đã nhận đủ tiền chuyển khoản.');return;}
        let receipt;
        if(complete(state,()=>{if(payment.checkId===null&&meta(payment.code).status==='open')meta(payment.code).status='payment';receipt=recordReceipt(payment.code,payment.checkId,quote,method,payment.values);},'Đã thanh toán thành công.','collect',payment.code)&&receipt){state.receiptId=receipt.id;go(state,'receipt');renderAll();}return;
      }
      if(action==='receipt'){
        if(!canCollect()){openSheet(state,{type:'denied'});return;}
        state.receiptId=Number(button.dataset.id);go(state,'receipt');return;
      }
      if(action==='print-receipt'){
        if(!canCollect()){openSheet(state,{type:'denied'});return;}
        openSheet(state,{type:'print',id:Number(button.dataset.id)});return;
      }
      if(action==='browser-print'){
        if(!canCollect())return;
        document.querySelector('#print-area')?.remove();
        const printArea=document.createElement('section');printArea.id='print-area';
        const snapshot=phone.querySelector('.sheet').cloneNode(true);snapshot.querySelectorAll('button').forEach(button=>button.remove());
        printArea.append(...snapshot.childNodes);document.body.append(printArea);window.print();return;
      }
      if(action==='area'){state.area=button.dataset.value;render(index,false);return;}
      if(action==='category'){state.category=button.dataset.value;render(index,false);return;}
      if(action==='account'){openSheet(state,{type:'account'});return;}
      if(action==='customer-info'){openSheet(state,{type:'customer-info'});return;}
      if(action==='clear-customer'){
        state.sheet.values={...state.sheet.values,customer_phone:''};delete state.sheet.values.customer_name;
        state.sheet.lookup=null;state.sheet.lookupError=null;render(index);return;
      }
      if(action==='lookup-customer'){
        const sheet=state.sheet;
        sheet.lookup=null;sheet.lookupError=null;
        if(!String(sheet.values?.customer_phone||'').trim()){render(index);return;}
        try{
          if(!online)throw new Error('Chưa có mạng để tra cứu. Hãy kết nối lại; không tự tạo hồ sơ khi chưa đối chiếu.');
          const phoneNumber=normalizedPhone(sheet.values?.customer_phone||'');
          sheet.values={...sheet.values,customer_phone:phoneNumber};
          const found=customers.find(item=>item.phone===phoneNumber);
          sheet.lookup={phone:phoneNumber,found:Boolean(found),id:found?.id};
        }catch(error){sheet.lookupError=error.message;}
        render(index);return;
      }
      if(action==='table-info'){openSheet(state,{type:'info'});return;}
      if(action==='close')state.sheet=null;
      if(action==='history'){openSheet(state,{type:'history'});return;}
      if(action==='restore-sheet'){
        const saved=state.sheet.restore;
        if(saved?.type==='checkout-confirm'&&state.checkout){state.checkout.version=meta(state.checkout.code).version;state.sheet=null;go(state,'checkout');return;}
        if(saved)openSheet(state,{...saved,version:meta(saved.code).version});else{state.sheet=null;render(index);}
        return;
      }
      if(action==='table'){
        const item=tables.find(item=>item.code===button.dataset.code);
        if(item.state==='reserved'){go(state,'bookings');return;}
        if(item.state==='cleaning'){openSheet(state,{type:'cleaning',code:item.code});return;}
        if(item.state==='available'){openSheet(state,{type:'open',code:item.code});return;}
        else{switchTable(item.code);go(state,'order');renderAll();return;}
      }
      if(action==='note'){openSheet(state,{type:'note',id:Number(button.dataset.id)});return;}
      if(action==='add'){if(meta().status==='open'&&attempt(state,()=>add(Number(button.dataset.id))))renderAll();return;}
      if(action==='plus'||action==='minus'){
        const item=order()[Number(button.dataset.index)];if(!item||item.status!=='draft')return;
        if(meta().status==='open'&&attempt(state,()=>{item.qty+=action==='plus'?1:-1;if(item.qty===0)order().splice(Number(button.dataset.index),1);}))renderAll();return;
      }
      if(action==='confirm-send'){openSheet(state,{type:'send'});return;}
      if(action==='send'){
        if(meta().status!=='open'||!order().some(item=>item.status==='draft')){notify(state,'Không có món mới hợp lệ để gửi.');return;}
        complete(state,()=>{order().forEach(item=>{if(item.status==='draft')item.status='pending';});record('Gửi món xuống bếp');},'Đã gửi món xuống bếp · Bàn '+selected);return;
      }
      if(action==='served'){openSheet(state,{type:'served',code:button.dataset.code,index:Number(button.dataset.index),version:meta(button.dataset.code).version});return;}
      if(action==='confirm-served'){
        const sheet=state.sheet,item=(orders[sheet.code]||[])[sheet.index];
        if(!item||item.status!=='ready'){notify(state,'Món không còn ở trạng thái chờ mang ra.');return;}
        complete(state,()=>{item.status='served';history.push({action:'Đã mang món ra',code:sheet.code,actor:roleNames[role]});},'Đã xác nhận phục vụ · Bàn '+sheet.code,'manage',sheet.code);return;
      }
      if(action==='booking-review'){const booking=bookings.find(item=>item.id===Number(button.dataset.id));openSheet(state,{type:'booking',id:booking.id,code:booking.table,version:meta(booking.table).version});return;}
      if(action==='booking-order'){switchTable(button.dataset.code);go(state,'order');renderAll();return;}
      if(action==='qr-review'||action==='qr-reject'){
        const request=qrRequests.find(item=>item.id===Number(button.dataset.id));if(!request)return;
        openSheet(state,{type:action==='qr-review'?'qr':'reject',id:request.id,code:request.table,version:meta(request.table).version});return;
      }
      if(action==='qr-customer'){
        const request=qrRequests.find(item=>item.id===state.sheet.id);if(!request||request.type!=='checkin')return;
        openSheet(state,{type:'open',code:request.table,qrId:request.id});return;
      }
      if(action==='confirm-qr'){
        const request=qrRequests.find(item=>item.id===state.sheet.id);if(!request)return;
        const target=tables.find(item=>item.code===request.table);
        if(request.type==='checkin'&&(target.state!=='available'||request.guests>target.seats)){notify(state,'Bàn không còn trống hoặc không đủ chỗ. Hãy kiểm tra lại.');return;}
        if(request.type==='order'&&(target.state!=='occupied'||meta(request.table).status!=='open')){notify(state,'Order không còn nhận thêm món. Không thể duyệt yêu cầu QR.');return;}
        if(complete(state,()=>{
          if(request.type==='checkin'){target.state='occupied';target.guests=request.guests;orders[request.table]=[];metadata[request.table]={version:1,status:'open',splits:[],source:'qr',note:'Nhận bàn từ yêu cầu QR'};}
          else(orders[request.table]||=[]).push({dishId:request.dishId,qty:request.qty,note:request.note,status:'pending'});
          qrRequests=qrRequests.filter(item=>item.id!==request.id);
          history.push({action:request.type==='checkin'?'Nhận bàn QR':'Duyệt món QR & gửi bếp',code:request.table,actor:roleNames[role]});
        },request.type==='checkin'?'Đã nhận bàn '+request.table:'Đã gửi riêng món QR xuống bếp','manage',request.table)){switchTable(request.table);go(state,request.type==='checkin'?'menu':'order');renderAll();}return;
      }
      if(action==='request'){
        const request=requests.find(item=>item.id===Number(button.dataset.id));if(!request)return;
        if(request.id===2||request.payment){switchTable(request.table);go(state,'order');renderAll();return;}
        complete(state,()=>{requests=requests.filter(item=>item.id!==request.id);history.push({action:'Hoàn tất yêu cầu phục vụ',code:request.table,actor:roleNames[role]});},'Đã đánh dấu yêu cầu được xử lý.','manage',request.table);return;
      }
      if(action==='cancel-item'){openSheet(state,{type:'cancel-item',index:Number(button.dataset.index)});return;}
      if(action==='cancel-order'){openSheet(state,{type:'cancel-order'});return;}
      if(action==='move'){openSheet(state,{type:'move'});return;}
      if(action==='payment'){openSheet(state,{type:'payment'});return;}
      if(action==='confirm-payment'){
        if(!canRequestPayment()){notify(state,'Chỉ gửi thanh toán khi mọi món đã phục vụ và chưa có yêu cầu trước đó.');return;}
        complete(state,()=>{meta().status='payment';if(!requests.some(item=>item.table===selected&&(item.id===2||item.payment)))requests.push({id:Date.now(),table:selected,title:'Yêu cầu thanh toán',detail:'Phục vụ đã kiểm tra toàn bộ món',payment:true});record('Yêu cầu thanh toán');},'Đã chuyển yêu cầu cho thu ngân.');return;
      }
      if(action==='split'){openSheet(state,{type:'split'});return;}
      if(action==='prepare-split'){
        if(!eligibleCheckout(selected)||meta().status!=='open')return;
        if(complete(state,()=>{meta().status='payment';record('Chuẩn bị tách hóa đơn');},'Order đã chuyển chờ thanh toán.','collect'))openSheet(state,{type:'split'});return;
      }
      if(action==='merge'){openSheet(state,{type:'merge',index:Number(button.dataset.index)});return;}
      if(action==='confirm-merge'){
        const check=meta().splits[state.sheet.index];if(!check||check.paid||meta().status!=='payment'){notify(state,'Không thể ghép hóa đơn đã thu hoặc đang có giao dịch chờ.');return;}
        complete(state,()=>{order().push(...check.items);meta().splits.splice(state.sheet.index,1);record('Ghép hóa đơn tách');},'Đã ghép về hóa đơn gốc. Tổng tiền của bàn giữ nguyên.','collect');return;
      }
      if(action==='finish-cleaning'){
        const code=state.sheet.code,item=tables.find(item=>item.code===code);
        if(item.state!=='cleaning')return;
        complete(state,()=>{item.state='available';history.push({action:'Dọn bàn xong',code,actor:roleNames[role]});},'Bàn '+code+' đã sẵn sàng nhận khách.','manage',code);return;
      }
      render(index);
      phone.querySelector('.sheet textarea,.sheet input,.sheet .primary,.sheet .secondary')?.focus({preventScroll:true});
    });
    phone.addEventListener('input',event=>{
      if(event.target.closest('.sheet form'))captureFields(phone,state);
      if(event.target.closest('[data-form="checkout"]')){
        captureFields(phone,state);
        if(event.target.name==='cash_received'){
          const change=phone.querySelector('[data-change]');
          if(change)change.textContent=money(Math.max(0,Number(event.target.value||0)-paymentQuote(state.checkout.code,state.checkout.checkId,state.checkout.promo).due));
        }
      }
      if(event.target.name==='customer_phone'&&state.sheet){
        state.sheet.lookup=null;state.sheet.lookupError=null;
        delete state.sheet.values.customer_name;
        phone.querySelector('[data-new-customer-fields]')?.remove();
        const clearButton=phone.querySelector('[data-action="clear-customer"]');
        if(clearButton)clearButton.hidden=!event.target.value.trim();
        const result=phone.querySelector('.customer-result');
        if(result){const hint=document.createElement('p');hint.className='field-hint';hint.textContent=event.target.value.trim()?'SĐT đã thay đổi. Bấm Tìm để đối chiếu trước khi mở bàn.':'Không cung cấp SĐT: tiếp tục phục vụ khách vãng lai.';result.replaceChildren(hint);}
      }
      if(!event.target.matches('[data-search]'))return;
      state.query=event.target.value;phone.querySelector('[data-menu-list]').innerHTML=dishList(state);
    });
    phone.addEventListener('submit',event=>{
      const form=event.target.closest('[data-form]');if(!form)return;event.preventDefault();
      captureFields(phone,state);
      const data=new FormData(form),type=form.dataset.form;
      if(type==='checkout'){
        if(!canCollect()){openSheet(state,{type:'denied'});return;}
        const payment=state.checkout;
        if(!eligibleCheckout(payment.code,payment.checkId)){formError(form,'Hóa đơn chưa đủ điều kiện thu tiền hoặc đã được thanh toán.');return;}
        if(payment.version!==meta(payment.code).version){openSheet(state,{type:'conflict',restore:{type:'checkout-confirm',code:payment.code}});return;}
        const code=String(data.get('promotion_code')||'').trim().toUpperCase();
        if(code!==(payment.promo||'')){formError(form,'Bấm Áp dụng để kiểm tra mã giảm giá trước khi xác nhận.');return;}
        const method=data.get('payment_method'),quote=paymentQuote(payment.code,payment.checkId,payment.promo);
        if(!['CASH','BANK_TRANSFER'].includes(method)){formError(form,'Chọn phương thức thanh toán.');return;}
        if(method==='CASH'&&(!/^\d+$/.test(String(data.get('cash_received')||''))||Number(data.get('cash_received'))<quote.due)){formError(form,'Tiền khách đưa phải đủ số cần thu và là số nguyên đồng.');return;}
        if(method==='BANK_TRANSFER'&&!data.get('received_transfer')){formError(form,'Xác nhận đã nhận đủ tiền chuyển khoản.');return;}
        openSheet(state,{type:'checkout-confirm',code:payment.code,version:payment.version});return;
      }
      if(['reject','cancel-item','cancel-order'].includes(type)&&!String(data.get('reason')||'').trim()){formError(form,'Vui lòng nhập lý do cụ thể, không chỉ khoảng trắng.');return;}
      if(type==='note'){
        if(meta().status!=='open'){formError(form,'Order không còn nhận thêm món.');return;}
        complete(state,()=>add(state.sheet.id,String(data.get('note')||'').trim()),'Đã thêm món kèm ghi chú.');
      }
      if(type==='open'){
        const code=state.sheet.code,item=tables.find(item=>item.code===code),guests=Number(data.get('guests'));
        if(item.state!=='available'||!Number.isInteger(guests)||guests<1||guests>item.seats){formError(form,'Bàn không còn trống hoặc số khách không hợp lệ.');return;}
        const rawPhone=String(data.get('customer_phone')||'').trim(),qrId=state.sheet.qrId;
        let profile=null,phoneNumber='',customerName='';
        if(rawPhone){
          try{phoneNumber=normalizedPhone(data.get('customer_phone')||'');}catch(error){formError(form,error.message);return;}
          if(!state.sheet.lookup||state.sheet.lookup.phone!==phoneNumber){formError(form,'Tra cứu lại SĐT và đối chiếu khách trước khi mở bàn.');return;}
          profile=customers.find(customer=>customer.phone===phoneNumber)||null;
          if(!profile){
            if(!canAddCustomer()){formError(form,'Tài khoản chưa có quyền thêm khách hàng.');return;}
            customerName=String(data.get('customer_name')||'').trim().replace(/\s+/g,' ');
            if(!customerName||customerName.length>150){formError(form,'Nhập họ tên khách từ 1 đến 150 ký tự, không chỉ khoảng trắng.');return;}
          }
        }
        const visitNote=String(data.get('visit_note')||'').trim();
        if(visitNote.length>1000){formError(form,'Ghi chú bàn không được vượt quá 1000 ký tự.');return;}
        if(qrId&&!qrRequests.some(request=>request.id===qrId&&request.type==='checkin')){formError(form,'Yêu cầu nhận bàn QR đã được xử lý.');return;}
        if(complete(state,()=>{
          if(!profile&&phoneNumber){profile={id:Math.max(0,...customers.map(customer=>customer.id))+1,name:customerName,phone:phoneNumber,tier:'Thành viên',discount:0,spending:0};customers.push(profile);history.push({action:'Tạo khách hàng '+profile.name,code,actor:roleNames[role]});}
          item.state='occupied';item.guests=guests;orders[code]=[];metadata[code]={version:1,status:'open',splits:[],customerId:profile?.id||null,source:qrId?'qr':'walkin',note:visitNote};
          if(qrId)qrRequests=qrRequests.filter(request=>request.id!==qrId);
          history.push({action:'Mở bàn · '+(profile?.name||'Khách vãng lai'),code,actor:roleNames[role]});
        },'Đã mở bàn '+code,'manage',code)){switchTable(code);go(state,'menu');renderAll();}
      }
      if(type==='booking'){
        const booking=bookings.find(item=>item.id===state.sheet.id),target=tables.find(item=>item.code===booking.table);
        if(!data.get('verified')||booking.status!=='confirmed'||target.state!=='reserved'||booking.guests>target.seats){formError(form,'Cần đối chiếu khách và kiểm tra lại tình trạng bàn.');return;}
        const visitNote=String(data.get('visit_note')||'').trim();
        if(visitNote.length>1000){formError(form,'Ghi chú bàn không được vượt quá 1000 ký tự.');return;}
        if(complete(state,()=>{booking.status='seated';target.state='occupied';target.guests=booking.guests;orders[booking.table]=[];metadata[booking.table]={version:1,status:'open',splits:[],booking:booking.id,customerId:booking.customerId,source:'booking',note:visitNote};history.push({action:'Nhận khách đặt bàn',code:booking.table,actor:roleNames[role]});},'Đã nhận khách '+booking.code,'manage',booking.table)){switchTable(booking.table);go(state,'menu');renderAll();}
      }
      if(type==='reject'){
        const request=qrRequests.find(item=>item.id===state.sheet.id);if(!request){formError(form,'Yêu cầu đã được xử lý.');return;}
        complete(state,()=>{qrRequests=qrRequests.filter(item=>item.id!==request.id);history.push({action:'Từ chối QR',reason:String(data.get('reason')).trim(),code:request.table,actor:roleNames[role]});},'Đã từ chối yêu cầu và lưu lý do.','manage',request.table);
      }
      if(type==='cancel-item'){
        const item=order()[state.sheet.index];if(!item||item.status==='cancelled'){formError(form,'Món đã được xử lý.');return;}
        if(meta().status!=='open'){formError(form,'Order đang chờ thanh toán, không thể hủy món tại đây.');return;}
        const permission=['cooking','ready','served'].includes(item.status)?'prepared':'manage';
        complete(state,()=>{item.status='cancelled';item.reason=String(data.get('reason')).trim();record('Hủy món '+dishById(item.dishId).name,item.reason);},'Đã hủy món và lưu lý do.',permission);
      }
      if(type==='cancel-order'){
        if(liveItems().some(item=>item.status!=='draft')||meta().status==='cancelled'){formError(form,'Không thể hủy cả order đã có món gửi bếp.');return;}
        complete(state,()=>{order().forEach(item=>{if(item.status==='draft'){item.status='cancelled';item.reason=String(data.get('reason')).trim();}});meta().status='cancelled';table().state='cleaning';record('Hủy bàn / order',String(data.get('reason')).trim());},'Đã hủy order. Bàn chuyển sang cần dọn.');
      }
      if(type==='move'){
        const target=tables.find(item=>item.code===data.get('target')),source=selected;
        if(!target||target.state!=='available'||target.seats<(table().guests||1)||meta().splits.length||meta().status==='cancelled'){formError(form,'Bàn đích không còn phù hợp hoặc order đã tách hóa đơn.');return;}
        if(complete(state,()=>{
          target.state='occupied';target.guests=table().guests;table().state='cleaning';orders[target.code]=order();delete orders[source];metadata[target.code]=meta();delete metadata[source];
          bookings.filter(item=>item.table===source&&item.status==='seated').forEach(item=>{item.table=target.code;});
          requests.filter(item=>item.table===source).forEach(item=>{item.table=target.code;});
          qrRequests.filter(item=>item.type==='order'&&item.table===source).forEach(item=>{item.table=target.code;});
          history.push({action:'Chuyển bàn '+source+' → '+target.code,code:source,actor:roleNames[role]});
        },'Đã chuyển toàn bộ order sang bàn '+target.code)){switchTable(target.code);go(state,'order');renderAll();}
      }
      if(type==='split'){
        if(!canCollect()||meta().status!=='payment'||!liveItems().every(item=>item.status==='served')){formError(form,'Chỉ tách hóa đơn chưa thu, đang chờ thanh toán và đã phục vụ xong mọi món.');return;}
        const quantities=order().map((item,index)=>Number(data.get('qty-'+index)||0));
        if(quantities.some((qty,index)=>!Number.isInteger(qty)||qty<0||qty>order()[index].qty)||!quantities.some(qty=>qty>0)||quantities.reduce((sum,qty)=>sum+qty,0)>=count(liveItems())){formError(form,'Chọn ít nhất một món và giữ lại ít nhất một món trong hóa đơn gốc.');return;}
        complete(state,()=>{
          const moved=[];order().forEach((item,index)=>{if(quantities[index]>0){moved.push({...item,qty:quantities[index]});item.qty-=quantities[index];}});
          orders[selected]=order().filter(item=>item.qty>0);meta().splits.push({id:++checkSequence,items:moved,customerId:meta().customerId||null,paid:false});record('Tách hóa đơn');
        },'Đã tạo hóa đơn tách. Tổng tiền của bàn giữ nguyên.','collect');
      }
    });
    phone.addEventListener('change',event=>{
      if(event.target.name==='payment_method'&&state.checkout){captureFields(phone,state);state.checkout.error='';render(index);}
    });
    phone.addEventListener('keydown',event=>{
      if(event.key==='Escape'&&state.sheet){state.sheet=null;render(index);}
      if(event.key==='Tab'&&state.sheet){
        const controls=[...phone.querySelectorAll('.sheet button,.sheet input,.sheet textarea,.sheet select')];
        const first=controls[0],last=controls[controls.length-1];
        if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
        else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
      }
    });
  });
  document.querySelectorAll('[data-mode]').forEach(button=>button.addEventListener('click',()=>{
    document.body.classList.toggle('single',button.dataset.mode==='single');
    document.querySelectorAll('[data-mode]').forEach(item=>{item.classList.toggle('selected',item===button);item.setAttribute('aria-pressed',String(item===button));});
  }));
  document.querySelector('#reset').addEventListener('click',()=>{
    resetState();role='service';document.querySelector('#demo-role').value=role;document.querySelector('#demo-scenario').value='';document.querySelector('#demo-add-customer').checked=true;settings.forEach((state,index)=>{window.clearTimeout(state.toastTimer);Object.assign(state,{screen:['tables','menu','order'][index],area:'Tầng 1',category:'Tất cả',query:'',sheet:null,toast:null,checkout:null,receiptId:null});});renderAll();
  });
  document.querySelector('#demo-role').addEventListener('change',event=>{
    role=event.target.value;settings.forEach(state=>{state.sheet=null;});renderAll();
  });
  document.querySelector('#demo-add-customer').addEventListener('change',()=>renderAll());
  document.querySelector('#demo-scenario').addEventListener('change',event=>{
    const scenario=event.target.value;
    if(scenario==='offline')online=false;
    if(scenario==='online')online=true;
    if(scenario==='failure')failNext=true;
    if(scenario==='conflict'){
      meta().version++;
      const pending=order().find(item=>item.status==='pending'||item.status==='cooking');
      if(pending)pending.status='ready';else if(meta().status==='open')order().push({dishId:3,qty:1,status:'pending',note:'Gọi thêm từ thiết bị khác'});
    }
    if(scenario==='ready'&&meta().status==='open'){
      let items=order().filter(item=>['pending','cooking'].includes(item.status));
      if(!items.length){const item={dishId:2,qty:1,status:'ready',note:'Không hành'};order().push(item);}else items.forEach(item=>{item.status='ready';});
      meta().version++;
    }
    if(scenario==='served'&&meta().status!=='paid'&&meta().status!=='cancelled'){order().forEach(item=>{if(item.status!=='cancelled')item.status='served';});meta().version++;}
    renderAll();event.target.value='';
  });
  let operationsView=false;
  const showOperations = enabled => {
    operationsView=enabled;
    const screens=enabled?['ready','bookings','requests']:['tables','menu','order'];
    const titles=enabled?['Mang món đúng bàn','Nhận khách đặt trước','Tiếp nhận yêu cầu QR']:['Bắt đầu từ bàn','Gọi món nhanh','Kiểm tra rồi gửi'];
    const descriptions=enabled?['Xác nhận sau khi đã mang món cho khách.','Đối chiếu thông tin trước khi nhận bàn.','Kiểm tra, duyệt hoặc từ chối có lý do.']:['Trạng thái rõ, việc cần làm ở ngay phía trên.','Tìm món, thêm một chạm, ghi chú khi cần.','Tách món mới và món đã gửi, tránh gửi nhầm.'];
    settings.forEach((state,index)=>{state.screen=screens[index];state.sheet=null;});
    document.querySelectorAll('.screen-caption h2').forEach((title,index)=>{title.textContent=titles[index];});
    document.querySelectorAll('.screen-caption p').forEach((text,index)=>{text.textContent=descriptions[index];});
    document.querySelector('#show-operations').textContent=enabled?'← Xem luồng gọi món chính':'Xem nghiệp vụ bổ sung →';
    renderAll();
  };
  document.querySelector('#show-operations').addEventListener('click',()=>showOperations(!operationsView));
  const showReception = () => {
    showOperations(false);
    const titles=['Nhận bàn có thông tin khách','Khách đi theo màn gọi món','Order giữ thông tin phục vụ'];
    document.querySelectorAll('.screen-caption h2').forEach((title,index)=>{title.textContent=titles[index];});
    document.querySelectorAll('.screen-caption p').forEach((text,index)=>{text.textContent=['Tra cứu SĐT, chọn khách và ghi chú bàn.','Luôn nhìn thấy tên, SĐT và hạng khách.','Phân biệt ghi chú bàn với ghi chú chế biến.'][index];});
    openSheet(settings[0],{type:'open',code:'B01',values:{customer_phone:'0901234567',guests:'2',visit_note:'Có trẻ em, ưu tiên bàn yên tĩnh'},lookup:{phone:'0901234567',found:true,id:1}});
  };
  document.querySelector('#show-reception').addEventListener('click',showReception);
  const showCashier = () => {
    showOperations(false);role='cashier';document.querySelector('#demo-role').value=role;
    const ready=unpaidChecks().find(check=>eligibleCheckout(check.code,check.checkId));
    if(ready)startCheckout(settings[1],ready.code,ready.checkId);else settings[1].screen='payments';
    settings[0].screen='payments';settings[2].screen='invoices';
    const titles=['Danh sách cần thu tiền','Thu tiền đúng hóa đơn','Tra cứu hóa đơn trong ca'];
    const descriptions=['Ưu tiên bàn đã phục vụ xong; chỉ rõ món còn chờ.','Kiểm tra ưu đãi, phương thức và tiền thừa.','Hóa đơn xuất hiện sau khi thanh toán thành công.'];
    document.querySelectorAll('.screen-caption h2').forEach((title,index)=>{title.textContent=titles[index];});
    document.querySelectorAll('.screen-caption p').forEach((text,index)=>{text.textContent=descriptions[index];});renderAll();
  };
  document.querySelector('#show-cashier').addEventListener('click',showCashier);
  if(new URLSearchParams(window.location.search).get('view')==='operations')showOperations(true);
  if(new URLSearchParams(window.location.search).get('view')==='reception')showReception();
  if(new URLSearchParams(window.location.search).get('view')==='cashier')showCashier();
  renderAll();
})();
