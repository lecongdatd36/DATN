document.addEventListener("DOMContentLoaded", () => {
    const page = document.querySelector("[data-qr-status-page]");
    const orderList = document.querySelector("[data-qr-status-list]");
    const orderEmpty = document.querySelector("[data-qr-status-empty]");
    const serviceList = document.querySelector("[data-service-status-list]");
    const serviceEmpty = document.querySelector("[data-service-status-empty]");
    if (!page || !orderList || !orderEmpty || !serviceList || !serviceEmpty) return;
    let etag = null;
    let timer = null;

    const statusClass = (value) => String(value || "").toLowerCase().replaceAll("_", "-");
    const renderOrders = (requests) => {
        orderList.replaceChildren();
        orderEmpty.hidden = requests.length > 0;
        requests.forEach((request) => {
            const card = document.createElement("article");
            card.className = `customer-qr-status-card is-${statusClass(request.status_code)}`;
            const header = document.createElement("header");
            const title = document.createElement("strong");
            title.textContent = request.code;
            const status = document.createElement("span");
            status.className = "customer-status-pill";
            status.textContent = request.status;
            header.append(title, status);
            const items = document.createElement("ul");
            request.items.forEach((item) => {
                const row = document.createElement("li");
                const name = document.createElement("span");
                name.textContent = `${item.name} × ${item.quantity}`;
                const itemStatus = document.createElement("strong");
                itemStatus.className = `is-${statusClass(item.status_code)}`;
                itemStatus.textContent = item.status;
                row.append(name, itemStatus);
                items.appendChild(row);
            });
            card.append(header, items);
            if (request.reject_reason) {
                const reason = document.createElement("p");
                reason.className = "customer-qr-status-reason";
                reason.textContent = `Lý do: ${request.reject_reason}`;
                card.appendChild(reason);
            }
            orderList.appendChild(card);
        });
    };

    const renderServices = (requests) => {
        serviceList.replaceChildren();
        serviceEmpty.hidden = requests.length > 0;
        requests.forEach((request) => {
            const card = document.createElement("article");
            card.className = `customer-qr-status-card is-${statusClass(request.status_code)}`;
            const header = document.createElement("header");
            const title = document.createElement("strong");
            title.textContent = request.request_type;
            const status = document.createElement("span");
            status.className = "customer-status-pill";
            status.textContent = request.status;
            header.append(title, status);
            card.appendChild(header);
            if (request.note) {
                const note = document.createElement("p");
                note.textContent = request.note;
                card.appendChild(note);
            }
            serviceList.appendChild(card);
        });
    };

    const render = (payload) => {
        renderOrders(payload.requests || []);
        renderServices(payload.service_requests || []);
    };
    render(JSON.parse(document.querySelector("#qr-status-data")?.textContent || "{}"));

    const schedule = () => {
        window.clearTimeout(timer);
        timer = window.setTimeout(poll, 7000);
    };
    const poll = async () => {
        if (document.hidden) {
            schedule();
            return;
        }
        try {
            const headers = {Accept: "application/json"};
            if (etag) headers["If-None-Match"] = etag;
            const response = await fetch(page.dataset.statusEndpoint, {headers, cache: "no-store"});
            if (response.status === 304) {
                schedule();
                return;
            }
            if (response.ok) {
                etag = response.headers.get("ETag");
                render(await response.json());
            }
        } catch (_) {
            // Keep the last known status visible when a poll is interrupted.
        }
        schedule();
    };
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) poll();
    });
    poll();
});
