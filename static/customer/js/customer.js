document.addEventListener("DOMContentLoaded", () => {
    const mobileLogin = document.querySelector("[data-mobile-login]");
    if (mobileLogin) {
        const mobileQuery = window.matchMedia("(max-width: 767.98px)");
        const syncLogin = () => { mobileLogin.value = mobileQuery.matches ? "1" : "0"; };
        syncLogin();
        mobileQuery.addEventListener("change", syncLogin);
    }
    const toggle = document.querySelector("[data-customer-menu-toggle]");
    const navigation = document.querySelector("#customer-navigation");

    if (toggle && navigation) {
        toggle.addEventListener("click", () => {
            const isOpen = navigation.classList.toggle("is-open");
            toggle.setAttribute("aria-expanded", String(isOpen));
            toggle.setAttribute("aria-label", isOpen ? "Đóng menu" : "Mở menu");
        });

        navigation.querySelectorAll("a").forEach((link) => {
            link.addEventListener("click", () => {
                navigation.classList.remove("is-open");
                toggle.setAttribute("aria-expanded", "false");
                toggle.setAttribute("aria-label", "Mở menu");
            });
        });
    }

    const heroImages = [...document.querySelectorAll("[data-customer-hero-carousel] .customer-hero-image")];
    if (heroImages.length > 1) {
        let currentImage = 0;
        window.setInterval(() => {
            heroImages[currentImage].classList.add("is-hidden");
            currentImage = (currentImage + 1) % heroImages.length;
            heroImages[currentImage].classList.remove("is-hidden");
        }, 5000);
    }
});