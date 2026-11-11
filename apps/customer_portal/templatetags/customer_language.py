from django import template
from django.utils.translation import gettext
from apps.customer_portal.localization import public_name, public_description

register = template.Library()
register.filter("public_name", public_name)
register.filter("public_description", public_description)
register.filter("public_text", lambda value: gettext(str(value)) if value is not None else "")


@register.filter
def public_item_name(item):
    source = getattr(item,"dish_name","")
    if getattr(item,"dish_id",None) and item.dish.name == source:
        return public_name(item.dish)
    return gettext(source)
