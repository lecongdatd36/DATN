import re
from urllib.parse import urlsplit, urlunsplit

from django.http import QueryDict
from django.urls import reverse


def is_mobile_request(request):
    """Use the login viewport when supplied, with a fallback for no JavaScript."""
    viewport = request.POST.get("mobile_view")
    if viewport in ("0", "1"):
        return viewport == "1"
    hint = request.headers.get("Sec-CH-UA-Mobile")
    if hint in ("?0", "?1"):
        return hint == "?1"
    return bool(re.search(r"Android|iPhone|iPod|Mobile", request.headers.get("User-Agent", ""), re.I))


def device_login_redirect(request, url):
    """Keep deep links while choosing the matching sales workspace at login."""
    parts = urlsplit(url)
    query = QueryDict(parts.query, mutable=True)
    desktop, mobile = reverse("sales:workspace"), reverse("sales:mobile")
    if parts.path == desktop and is_mobile_request(request) and query.get("desktop") != "1":
        path = mobile
        if "open_table" in query:
            query["table"] = query.pop("open_table")[-1]
            query["page"] = "open"
        elif "order" in query or "table" in query:
            query["page"] = "menu" if parts.fragment == "sales-menu" else "order"
    elif parts.path == mobile and not is_mobile_request(request):
        path = desktop
        if query.get("page") == "open" and "table" in query:
            query["open_table"] = query.pop("table")[-1]
        query.pop("page", None)
    else:
        return url
    return urlunsplit((parts.scheme, parts.netloc, path, query.urlencode(), parts.fragment))


def mobile_tables_url(params):
    query = QueryDict(mutable=True)
    for key in ("area", "q"):
        if params.get(key):
            query[key] = params[key]
    status = {"empty": "AVAILABLE", "occupied": "OCCUPIED", "reserved": "RESERVED", "cleaning": "CLEANING"}.get(params.get("status"))
    if status:
        query["status"] = status
    suffix = query.urlencode()
    return reverse("sales:mobile") + ("?" + suffix if suffix else "")
