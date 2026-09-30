document.addEventListener("DOMContentLoaded", () => {
  const workspace = document.querySelector(".sales-workspace");
  if (!workspace) return;

  const search = workspace.querySelector("[data-dish-search]");
  const categoryButtons = [...workspace.querySelectorAll("[data-category-filter] button")];
  const cards = [...workspace.querySelectorAll("[data-dish-grid] .dish-card")];
  const empty = workspace.querySelector("[data-dish-empty]");
  let category = "all";

  const normalize = (value) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
  const filterDishes = () => {
    const query = normalize(search?.value || "");
    let visible = 0;
    cards.forEach((card) => {
      const categoryMatches = category === "all" || card.dataset.category === category;
      const textMatches = !query || normalize(card.dataset.dishName || "").includes(query);
      card.hidden = !(categoryMatches && textMatches);
      if (!card.hidden) visible += 1;
    });
    if (empty) empty.hidden = visible !== 0;
  };

  search?.addEventListener("input", filterDishes);
  categoryButtons.forEach((button) => button.addEventListener("click", () => {
    category = button.dataset.category || "all";
    categoryButtons.forEach((item) => item.classList.toggle("active", item === button));
    filterDishes();
  }));

  if (window.location.hash && window.bootstrap) {
    const trigger = workspace.querySelector(`[data-bs-target="${window.location.hash}"]`);
    if (trigger) window.bootstrap.Tab.getOrCreateInstance(trigger).show();
  }

  const openTable = new URLSearchParams(window.location.search).get("open_table");
  if (openTable && window.bootstrap) {
    const modal = document.getElementById(`open-table-${openTable}`);
    if (modal) window.bootstrap.Modal.getOrCreateInstance(modal).show();
  }
});
