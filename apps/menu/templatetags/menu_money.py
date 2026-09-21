from django import template

register = template.Library()


@register.filter
def dong(value):
    """Whole VND amounts, independent of the browser/server locale."""
    return format(value, ",.0f").replace(",", ".")
