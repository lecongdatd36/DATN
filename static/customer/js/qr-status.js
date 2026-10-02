document.addEventListener("DOMContentLoaded", () => {
    const page = document.querySelector("[data-qr-status-page]");
    const list = document.querySelector("[data-qr-status-list]");
    const empty = document.querySelector("[data-qr-status-empty]");
    if (!page || !list || !empty) return;

    const render = (requests) => {
        list.replaceChildren();
        empty.hidden = requests.length > 0;
        requests.forEach((request) => {
            const card = document.createElement("article");
            card.className = "customer-qr-status-card";
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
                itemStatus.textContent = item.status;
                row.append(name, itemStatus);
                items.appendChild(row);
            });
            card.append(header, items);
            list.appendChild(card);
        });
    };

    render(JSON.parse(document.querySelector("#qr-status-data")?.textContent || "[]"));
    const poll = async () => {
        try {
            const response = await fetch(page.dataset.statusEndpoint, { headers: { Accept: "application/json" } });
            if (response.ok) render((await response.json()).requests || []);
        } catch (_) {
            // Keep the last known status visible when a poll is interrupted.
        }
    };
    window.setInterval(poll, 7000);
});