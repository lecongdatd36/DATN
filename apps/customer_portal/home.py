"""Read-only presentation data for the public Cơm Quê homepage."""
from apps.menu.models import Dish

from .selectors import customer_categories


def homepage_context():
    categories = list(customer_categories(with_dishes=True))
    category_order = {"món chính": 0, "khai vị": 1, "món rau": 2, "đồ uống": 3, "tráng miệng": 4}
    categories.sort(key=lambda item: (category_order.get(item.name.casefold(), 5), item.name))

    def dish_order(dish):
        return (dish.status != Dish.Status.AVAILABLE,
                not dish.name.casefold().startswith("cơm"),
                category_order.get(dish.category.name.casefold(), 5), dish.name, dish.pk)

    dishes = sorted([dish for category in categories for dish in category.customer_dishes], key=dish_order)
    photographs = [dish for dish in dishes if dish.image or dish.thumbnail]
    available_photos = [dish for dish in photographs if dish.status == Dish.Status.AVAILABLE]
    hero_dishes = (available_photos or photographs)[:4]
    primary = hero_dishes[0] if hero_dishes else (dishes[0] if dishes else None)

    def photo_for(group, fallback):
        return next((dish for dish in available_photos if dish.category.name.casefold() == group), fallback)

    home_categories = []
    for category in categories:
        group = sorted(category.customer_dishes, key=dish_order)
        cover = next((dish for dish in group if dish.image or dish.thumbnail), None)
        home_categories.append({"id": category.pk, "name": category.name, "count": len(group), "cover": cover})
    return {
        "featured_dishes": dishes[:6], "menu_dishes": dishes,
        "hero_dishes": hero_dishes, "primary_dish": primary,
        "dessert_dish": photo_for("tráng miệng", primary),
        "drink_dish": next((dish for dish in available_photos if dish.name.casefold().startswith("trà")), photo_for("đồ uống", primary)),
        "sharing_dish": photo_for("khai vị", primary),
        "home_categories": home_categories, "menu_categories": categories,
        "menu_dish_count": len(dishes),
    }
