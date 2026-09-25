"use strict";

(() => {
    const uploadPreview = document.querySelector("[data-upload-preview]");
    const upload = document.querySelector("[data-dish-upload]");
    if (uploadPreview && upload) {
        const img = uploadPreview.querySelector("img");
        const clear = document.querySelector('[name="image-clear"]');
        let objectUrl;
        function refresh() {
            if (objectUrl) URL.revokeObjectURL(objectUrl);
            objectUrl = undefined;
            const file = upload.files?.[0];
            if (!clear?.checked && file && ["image/jpeg", "image/png", "image/webp"].includes(file.type) && file.size <= 5 * 1024 * 1024) {
                objectUrl = URL.createObjectURL(file);
                img.src = objectUrl;
            } else {
                img.src = clear?.checked ? uploadPreview.dataset.placeholderUrl : (uploadPreview.dataset.originalUrl || uploadPreview.dataset.placeholderUrl);
            }
        }
        upload.addEventListener("change", () => {
            if (upload.files?.length && clear) clear.checked = false;
            refresh();
        });
        clear?.addEventListener("change", refresh);
        window.addEventListener("pagehide", () => { if (objectUrl) URL.revokeObjectURL(objectUrl); });
    }

    const dishSelect = document.querySelector("[data-dish-select]");
    const selectedPreview = document.querySelector("[data-selected-dish-preview]");
    if (dishSelect && selectedPreview) {
        const img = selectedPreview.querySelector("img");
        function refresh() {
            const option = dishSelect.selectedOptions[0];
            img.src = option?.dataset.imageUrl || selectedPreview.dataset.placeholderUrl;
            img.alt = option?.value ? `Ảnh minh họa: ${option.textContent}` : "Chưa chọn món";
        }
        dishSelect.addEventListener("change", refresh);
        refresh();
    }
})();
