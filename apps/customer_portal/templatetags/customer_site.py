"""Public menu photographs for the shared restaurant layout."""
from django import template

from ..home import homepage_context

register = template.Library()


@register.simple_tag(takes_context=True)
def customer_site(context):
    # The homepage has already loaded this data; reuse its two-query snapshot.
    if "home_categories" in context:
        return {key: context.get(key) for key in ("home_categories", "primary_dish")}
    return homepage_context()
