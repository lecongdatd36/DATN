from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.menu.recommendations import dish_recommendations


@require_GET
def menu_recommendations(request):
    raw_ids = request.GET.getlist("dish")
    if len(raw_ids) > 50 or any(not value.isascii() or not value.isdecimal() or len(value) > 19
                                or not 0 < int(value) < 2**63 for value in raw_ids):
        return JsonResponse({"error": "Danh sách món không hợp lệ."}, status=400)
    response = JsonResponse({"items": dish_recommendations({int(value) for value in raw_ids})})
    response["Cache-Control"] = "no-store"
    return response
