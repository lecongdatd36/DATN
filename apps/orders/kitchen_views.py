from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from .models import OrderItem
from .permissions import has_order_permission
from .services import transition_item


class KitchenAccessMixin(AccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not has_order_permission(request.user, "work_kitchen"):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


class KitchenWorkspaceView(KitchenAccessMixin, TemplateView):
    template_name = "staff/kitchen/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queue = OrderItem.objects.filter(status__in=(OrderItem.Status.PENDING, OrderItem.Status.COOKING, OrderItem.Status.READY)).select_related("order__table")
        context.update(
            pending=queue.filter(status=OrderItem.Status.PENDING),
            cooking=queue.filter(status=OrderItem.Status.COOKING),
            ready=queue.filter(status=OrderItem.Status.READY),
        )
        return context


class KitchenStateView(KitchenAccessMixin, View):
    def get(self, request):
        items = list(OrderItem.objects.filter(status__in=(OrderItem.Status.PENDING, OrderItem.Status.COOKING, OrderItem.Status.READY)).values("id", "order_id", "status", "updated_at" if hasattr(OrderItem, "updated_at") else "created_at"))
        return JsonResponse({"items": items})


class KitchenTransitionView(KitchenAccessMixin, View):
    def post(self, request, item_id, target):
        item = OrderItem.objects.select_related("order").get(pk=item_id)
        try:
            transition_item(actor=request.user, order_id=item.order_id, item_id=item.pk, expected_revision=item.order.revision, target=target)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, "Đã cập nhật trạng thái món.")
        return redirect("kitchen:workspace")
