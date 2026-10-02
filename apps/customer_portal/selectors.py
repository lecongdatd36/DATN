from django.db.models import Prefetch

from apps.menu.models import Category, Dish


def customer_categories():
    available_dishes = Dish.objects.select_related("category", "unit").filter(
        status__in=(Dish.Status.AVAILABLE, Dish.Status.SOLD_OUT),
        category__is_active=True,
        unit__is_active=True,
    )
    return Category.objects.filter(is_active=True).prefetch_related(
        Prefetch("dishes", queryset=available_dishes, to_attr="customer_dishes")
    ).order_by("name", "pk")


def customer_dishes(*, query="", category_id=None):
    result = Dish.objects.select_related("category", "unit").filter(
        status__in=(Dish.Status.AVAILABLE, Dish.Status.SOLD_OUT),
        category__is_active=True,
        unit__is_active=True,
    )
    if query:
        result = result.filter(name__icontains=query)
    if category_id:
        result = result.filter(category_id=category_id)
    return result.order_by("category__name", "name", "pk")


def customer_dish_detail(pk):
    return Dish.objects.select_related("category", "unit").filter(
        pk=pk,
        status__in=(Dish.Status.AVAILABLE, Dish.Status.SOLD_OUT),
        category__is_active=True,
        unit__is_active=True,
    ).first()