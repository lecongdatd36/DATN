from django.db.models import Count, Q
from .models import Dish


def catalog_entries(model, *, q="", status=""):
    result = model.objects.annotate(dish_count=Count("dishes")).order_by("name", "pk")
    if q:
        result = result.filter(name__icontains=q)
    if status:
        result = result.filter(is_active=status == "active")
    return result


def dishes(*, q="", category=None, unit=None, status=""):
    result = Dish.objects.select_related("category", "unit")
    if q:
        result = result.filter(Q(code__icontains=q) | Q(name__icontains=q))
    if category:
        result = result.filter(category=category)
    if unit:
        result = result.filter(unit=unit)
    if status == "paused":
        result = result.exclude(status=Dish.Status.INACTIVE).filter(Q(category__is_active=False) | Q(unit__is_active=False))
    elif status == Dish.Status.INACTIVE:
        result = result.filter(status=status)
    elif status:
        result = result.filter(status=status, category__is_active=True, unit__is_active=True)
    return result
