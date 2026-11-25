var cqTranslate_customer = window.gettext || (text => text);
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

    const bookingPanel = document.querySelector('[data-quick-booking-panel]');
    if (bookingPanel) {
        const mobileBooking = window.matchMedia('(max-width: 760px)');
        const syncBooking = () => { bookingPanel.open = !mobileBooking.matches; };
        syncBooking();
        mobileBooking.addEventListener('change', syncBooking);
    }

    const categoryNavigation = document.querySelector('.customer-menu-filters');
    if (categoryNavigation) {
        const revealCategory = () => {
            const selected = categoryNavigation.querySelector('[aria-current="true"]');
            if (!selected || categoryNavigation.scrollWidth <= categoryNavigation.clientWidth) return;
            categoryNavigation.scrollLeft += selected.getBoundingClientRect().left
                - categoryNavigation.getBoundingClientRect().left
                - (categoryNavigation.clientWidth - selected.offsetWidth) / 2;
        };
        revealCategory();
        window.matchMedia('(max-width: 760px)').addEventListener('change', revealCategory);
    }

    if (toggle && navigation) {
        const closeNavigation = (restoreFocus = false) => {
            navigation.classList.remove('is-open');
            toggle.setAttribute('aria-expanded', 'false');
            toggle.setAttribute('aria-label', cqTranslate_customer('Mở menu'));
            if (restoreFocus) toggle.focus();
        };
        toggle.addEventListener("click", () => {
            const isOpen = navigation.classList.toggle("is-open");
            toggle.setAttribute("aria-expanded", String(isOpen));
            toggle.setAttribute("aria-label", isOpen ? cqTranslate_customer("Đóng menu") : cqTranslate_customer("Mở menu"));
        });

        navigation.querySelectorAll("a").forEach((link) => {
            link.addEventListener("click", () => {
                closeNavigation();
            });
        });
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && navigation.classList.contains('is-open')) closeNavigation(true);
        });
        document.addEventListener('click', event => {
            if (!navigation.contains(event.target) && !toggle.contains(event.target)) closeNavigation();
        });
        window.matchMedia('(max-width: 1100px)').addEventListener('change', () => closeNavigation());
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
