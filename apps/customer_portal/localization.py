"""Presentation only: original names, snapshots and financial values stay intact."""
from django.utils.translation import get_language, gettext


def english():
    return (get_language() or "vi").startswith("en")


def public_name(item):
    if isinstance(item, dict):
        source, translated = item.get("name", ""), item.get("name_en", "")
    else:
        source, translated = getattr(item, "name", ""), getattr(item, "name_en", "")
    return (translated or gettext(source)) if english() else source


def public_description(item):
    if isinstance(item, dict):
        source, translated = item.get("description", ""), item.get("description_en", "")
    else:
        source, translated = getattr(item, "description", ""), getattr(item, "description_en", "")
    return (translated or gettext(source)) if english() else source
