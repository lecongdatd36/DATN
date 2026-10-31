from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_GET

from core.context_processors import access_policy
from core.http import conditional_json_response
from core.notifications import notification_snapshot


@login_required
@require_GET
def notification_state(request):
    if not request.user.is_active:
        return HttpResponseForbidden()
    payload = notification_snapshot(
        access_policy(request)["access"], mobile=request.GET.get("mobile") == "1"
    )
    return conditional_json_response(request, payload)
