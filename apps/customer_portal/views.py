import json

from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.views import View
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, ListView, TemplateView
from django.views.decorators.csrf import ensure_csrf_cookie

from apps.menu.models import Dish
from apps.orders.models import Order, QROrderRequest
from apps.orders.services import create_qr_order_request
from apps.seating.models import DiningTableQRToken

from .selectors import customer_categories, customer_dish_detail, customer_dishes


class CustomerMenuView(ListView):
    template_name = "customer/menu_list.html"
    context_object_name = "dishes"

    def get_queryset(self):
        return customer_dishes(
            query=self.request.GET.get("q", "").strip(),
            category_id=self.request.GET.get("category", ""),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = customer_categories()
        context["query"] = self.request.GET.get("q", "").strip()
        context["selected_category"] = self.request.GET.get("category", "")
        return context


class CustomerHomeView(TemplateView):
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dishes = customer_dishes()
        context["featured_dishes"] = dishes[:3]
        context["hero_dishes"] = dishes.filter(image__gt="")[:8]
        context["menu_categories"] = customer_categories()
        return context


class CustomerDishDetailView(DetailView):
    template_name = "customer/dish_detail.html"
    context_object_name = "dish"

    def get_object(self, queryset=None):
        dish = customer_dish_detail(self.kwargs["pk"])
        if dish is None:
            raise Http404("Món không còn được phục vụ.")
        return dish

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["suggested_dishes"] = customer_dishes(category_id=self.object.category_id).exclude(pk=self.object.pk)[:3]
        return context


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CustomerQRTableView(DetailView):
    template_name = "customer/qr_menu.html"
    context_object_name = "qr_token"
    queryset = DiningTableQRToken.objects.select_related("table__area")

    def get_object(self, queryset=None):
        token = self.get_queryset().filter(token=self.kwargs["token"]).first()
        if token is None:
            raise Http404("Mã QR không tồn tại.")
        return token

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        token = self.object
        if token is None or not token.is_valid:
            context["qr_error"] = "Mã QR không hợp lệ hoặc đã hết hiệu lực."
            return context
        active_orders = Order.objects.filter(
            table=token.table,
            status__in=(Order.Status.OPEN, Order.Status.IN_PROGRESS),
        ).order_by("-opened_at", "-pk")
        orders = list(active_orders[:2])
        if token.table.status != token.table.Status.OCCUPIED:
            context["qr_error"] = "Bàn hiện chưa được mở. Vui lòng liên hệ nhân viên."
        elif len(orders) != 1:
            context["qr_error"] = "Bàn chưa có đúng một đơn đang phục vụ. Vui lòng liên hệ nhân viên."
        else:
            context["table"] = token.table
            context["order"] = orders[0]
            context["categories"] = customer_categories()
            context["dishes"] = customer_dishes()
        return context


class CustomerQRRequestView(View):
    def post(self, request, token):
        try:
            payload = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Dữ liệu giỏ hàng không hợp lệ."}, status=400)
        try:
            qr_request = create_qr_order_request(
                token=token,
                items=payload.get("items"),
                note=payload.get("note", ""),
            )
        except ValidationError as error:
            messages = error.messages if hasattr(error, "messages") else [str(error)]
            return JsonResponse({"error": messages[0]}, status=400)
        request_ids = [str(value) for value in request.session.get("qr_request_ids", []) if str(value).isdigit()]
        request_ids.append(str(qr_request.pk))
        request.session["qr_request_ids"] = request_ids[-20:]
        return JsonResponse({
            "request_id": qr_request.pk,
            "request_code": str(qr_request),
            "status": qr_request.get_status_display(),
            "status_url": reverse("customer_portal:qr_status", args=[token]),
        }, status=201)


class CustomerQRStatusMixin:
    def get_token(self):
        token = DiningTableQRToken.objects.select_related("table__area").filter(token=self.kwargs["token"]).first()
        if token is None or not token.is_valid:
            raise Http404("Mã QR không hợp lệ hoặc đã hết hiệu lực.")
        return token

    def get_requests(self, token):
        request_ids = [int(value) for value in self.request.session.get("qr_request_ids", []) if str(value).isdigit()]
        return QROrderRequest.objects.filter(
            pk__in=request_ids, table_id=token.table_id,
        ).select_related("order", "table__area").prefetch_related("items__dish", "items__order_item").order_by("-created_at")

    @staticmethod
    def serialize_requests(requests):
        return [{
            "code": str(qr_request),
            "status": qr_request.get_status_display(),
            "created_at": qr_request.created_at.isoformat(),
            "items": [{
                "name": item.dish.name,
                "quantity": item.quantity,
                "status": item.order_item.get_status_display() if item.order_item else qr_request.get_status_display(),
            } for item in qr_request.items.all()],
        } for qr_request in requests]


class CustomerQRStatusView(CustomerQRStatusMixin, TemplateView):
    template_name = "customer/qr_status.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        token = self.get_token()
        context["table"] = token.table
        context["qr_token"] = token
        context["status_data"] = self.serialize_requests(self.get_requests(token))
        context["status_endpoint"] = f"/menu/table/{token.token}/status/data/"
        return context


class CustomerQRStatusDataView(CustomerQRStatusMixin, View):
    def get(self, request, token):
        token = self.get_token()
        return JsonResponse({"requests": self.serialize_requests(self.get_requests(token))})
