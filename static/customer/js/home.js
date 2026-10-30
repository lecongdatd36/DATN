document.addEventListener("DOMContentLoaded", () => {
    "use strict";
    const root = document.querySelector("[data-cq-home]");
    if (!root) return;

    const cards = [...root.querySelectorAll("[data-cq-dish]")];
    const filters = [...root.querySelectorAll("[data-cq-category]")];
    const more = root.querySelector("[data-cq-show-more]");
    const empty = root.querySelector("[data-cq-empty]");
    const label = root.querySelector("[data-cq-menu-label]");
    let category = "all";
    let expanded = false;

    function renderDishes() {
        const matched = cards.filter(card => category === "all" || card.dataset.category === category);
        const visible = new Set(expanded || category !== "all" ? matched : matched.slice(0, 6));
        cards.forEach(card => { card.hidden = !visible.has(card); });
        if (more) more.hidden = category !== "all" || expanded || matched.length <= 6;
        if (empty) empty.hidden = matched.length !== 0 || cards.length === 0;
        const selected = filters.find(button => button.dataset.cqCategory === category);
        const title = category === "all" ? "Món ngon cho bữa cơm nhà" : selected?.querySelector("span")?.textContent || "Thực đơn";
        if (label) label.textContent = `${title} · ${visible.size} món`;
        filters.forEach(button => {
            const active = button.dataset.cqCategory === category;
            button.classList.toggle("is-active", active);
            button.setAttribute("aria-pressed", String(active));
        });
    }
    filters.forEach(button => button.addEventListener("click", () => {
        category = button.dataset.cqCategory;
        expanded = false;
        renderDishes();
    }));
    more?.addEventListener("click", () => { expanded = true; renderDishes(); });
    renderDishes();

    const hero = root.querySelector(".cq-hero");
    const slides = [...root.querySelectorAll("[data-cq-hero-slide]")];
    const dots = [...root.querySelectorAll("[data-cq-hero-dot]")];
    const caption = root.querySelector("[data-cq-hero-caption]");
    if (slides.length <= 1) return;
    let index = 0;
    let timer;
    let pausedByUser = false;
    const pause = root.querySelector("[data-cq-hero-pause]");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (pause) pause.hidden = reducedMotion.matches;
    function selectSlide(next) {
        index = (next + slides.length) % slides.length;
        slides.forEach((slide, position) => slide.classList.toggle("is-active", position === index));
        dots.forEach((dot, position) => {
            dot.classList.toggle("is-active", position === index);
            dot.setAttribute("aria-pressed", String(position === index));
        });
        if (caption) caption.textContent = slides[index].dataset.caption || "";
    }
    function stop() { window.clearInterval(timer); timer = undefined; }
    function start() {
        stop();
        if (!pausedByUser && !reducedMotion.matches && !document.hidden) timer = window.setInterval(() => selectSlide(index + 1), 6500);
    }
    function setPaused(value) {
        pausedByUser = value;
        if (pause) {
            pause.textContent = value ? "▶" : "Ⅱ";
            pause.setAttribute("aria-pressed", String(value));
            pause.setAttribute("aria-label", value ? "Tiếp tục chuyển ảnh" : "Tạm dừng chuyển ảnh");
        }
        value ? stop() : start();
    }
    pause?.addEventListener("click", () => setPaused(!pausedByUser));
    root.querySelector("[data-cq-hero-prev]")?.addEventListener("click", () => { selectSlide(index - 1); setPaused(true); });
    root.querySelector("[data-cq-hero-next]")?.addEventListener("click", () => { selectSlide(index + 1); setPaused(true); });
    dots.forEach((dot, position) => dot.addEventListener("click", () => { selectSlide(position); setPaused(true); }));
    hero?.addEventListener("mouseenter", stop);
    hero?.addEventListener("mouseleave", start);
    hero?.addEventListener("focusin", stop);
    hero?.addEventListener("focusout", event => { if (!hero.contains(event.relatedTarget)) start(); });
    document.addEventListener("visibilitychange", () => document.hidden ? stop() : start());
    reducedMotion.addEventListener("change", () => { if (pause) pause.hidden = reducedMotion.matches; start(); });
    start();
});
