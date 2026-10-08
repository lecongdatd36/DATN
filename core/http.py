import hashlib
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponseNotModified, JsonResponse


def conditional_json_response(request, payload):
    """Return compact JSON with an ETag so polling clients can receive 304."""
    encoded = json.dumps(
        payload,
        cls=DjangoJSONEncoder,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    etag = f'"{hashlib.sha256(encoded).hexdigest()}"'

    if request.headers.get("If-None-Match") == etag:
        response = HttpResponseNotModified()
    else:
        response = JsonResponse(payload, json_dumps_params={"ensure_ascii": False})
    response["ETag"] = etag
    response["Cache-Control"] = "private, no-cache"
    return response
