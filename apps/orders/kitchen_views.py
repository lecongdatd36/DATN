from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Count, Max
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from core.http import conditional_json_response

from .models import Order, OrderItem
from .permissions import has_order_permission
from .services import transition_item


class KitchenAccessMixin(AccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not has_order_permission(request.user, "work_kitchen"):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


def _sla_details(item, now=None):
    now = now or timezone.now()
    if item.status == OrderItem.Status.PENDING:
        anchor = item.sent_at or item.created_at
        threshold = settings.KITCHEN_PENDING_SLA_MINUTES
        prefix = "Chờ"
    elif item.status == OrderItem.Status.COOKING:
        anchor = item.started_at or item.sent_at or item.created_at
        threshold = settings.KITCHEN_COOKING_SLA_MINUTES
        prefix = "Đang làm"
    else:
        anchor = item.ready_at or item.updated_at
        threshold = settings.KITCHEN_READY_SLA_MINUTES
        prefix = "Chờ nhận"

    elapsed = max(0, int((now - anchor).total_seconds() // 60))
    warning_at = max(1, int(threshold * 0.7))
    level = "overdue" if elapsed >= threshold else "warning" if elapsed >= warning_at else "normal"
    return {
        "anchor": anchor,
        "elapsed": elapsed,
        "threshold": threshold,
        "prefix": prefix,
        "level": level,
    }


def _decorate_sla(item, now):
    details = _sla_details(item, now)
    item.sla_anchor = details["anchor"]
    item.sla_elapsed = details["elapsed"]
    item.sla_threshold = details["threshold"]
    item.sla_prefix = details["prefix"]
    item.sla_level = details["level"]
    return item


def _queue_queryset():
    return (
        OrderItem.objects.filter(
            status__in=(OrderItem.Status.PENDING, OrderItem.Status.COOKING, OrderItem.Status.READY),
            order__status__in=(Order.Status.OPEN, Order.Status.IN_PROGRESS),
        )
        .select_related("order__table")
        .order_by("sent_at", "pk")
    )


def _queue_counts():
    rows = _queue_queryset().order_by().values("status").annotate(total=Count("pk"))
    counts = {status: 0 for status in (OrderItem.Status.PENDING, OrderItem.Status.COOKING, OrderItem.Status.READY)}
    counts.update({row["status"]: row["total"] for row in rows})
    return counts


class KitchenWorkspaceView(KitchenAccessMixin, TemplateView):
    template_name = "staff/kitchen/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        queue = [_decorate_sla(item, now) for item in _queue_queryset()]
        context.update(
            pending=[item for item in queue if item.status == OrderItem.Status.PENDING],
            cooking=[item for item in queue if item.status == OrderItem.Status.COOKING],
            ready=[item for item in queue if item.status == OrderItem.Status.READY],
        )
        return context


class KitchenStateView(KitchenAccessMixin, View):
    def get(self, request):
        queue = _queue_queryset()
        payload = {
            "ui_version": "kitchen-2026-10-09.1",
            "queue": queue.aggregate(count=Count("pk"), latest=Max("updated_at")),
        }
        return conditional_json_response(request, payload)


class KitchenTransitionView(KitchenAccessMixin, View):
    def post(self, request, item_id, target):
        is_async = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        item = OrderItem.objects.select_related("order").get(pk=item_id)
        try:
            item = transition_item(
                actor=request.user,
                order_id=item.order_id,
                item_id=item.pk,
                expected_revision=item.order.revision,
                target=target,
            )
        except ValidationError as error:
            if is_async:
                return JsonResponse({"error": " ".join(error.messages)}, status=400)
            messages.error(request, " ".join(error.messages))
        else:
            if is_async:
                details = _sla_details(item)
                next_target = OrderItem.Status.READY if item.status == OrderItem.Status.COOKING else ""
                return JsonResponse(
                    {
                        "ok": True,
                        "item_id": item.pk,
                        "status": item.status,
                        "next_target": next_target,
                        "next_url": reverse("kitchen:transition", args=[item.pk, next_target]) if next_target else "",
                        "next_label": "Hoàn thành" if next_target else "",
                        "sla": {
                            "anchor": details["anchor"].isoformat(),
                            "threshold": details["threshold"],
                            "prefix": details["prefix"],
                            "level": details["level"],
                        },
                        "counts": _queue_counts(),
                    }
                )
            messages.success(request, "Đã cập nhật trạng thái món.")
        return redirect("kitchen:workspace")
