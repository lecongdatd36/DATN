from django import template
from decimal import Decimal
from django.utils.translation import get_language

register = template.Library()


@register.filter
def dong(value):
    """Whole VND amounts, independent of the browser/server locale."""
    amount = format(Decimal(value), ",.0f")
    return amount if (get_language() or "vi").startswith("en") else amount.replace(",", ".")
