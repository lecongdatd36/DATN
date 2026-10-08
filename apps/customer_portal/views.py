import json

from django.core.exceptions import ValidationError
from django.db.models import Count, Max
from django.http import Http404, JsonResponse
from django.views import View
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, ListView, TemplateView
from django.views.decorators.csrf import ensure_csrf_cookie

from apps.menu.models import Category, Dish, Unit
from apps.orders.models import Order, QRCheckInRequest, QROrderRequest, QRServiceRequest
from apps.orders.services import (
    create_qr_check_in_request,
    create_qr_order_request,
    create_qr_service_request,
    expire_qr_check_in_requests,
)
from apps.seating.models import DiningTableQRToken
from core.http import conditional_json_response

from .selectors import customer_categories, customer_dish_detail, customer_dishes


def _active_qr_orders(table):
    return list(Order.objects.filter(
        table=table,
        status__in=(Order.Status.OPEN, Order.Status.IN_PROGRESS),
    ).order_by("-opened_at", "-pk")[:2])


def _validation_message(error):
    messages = error.messages if hasattr(error, "messages") else [str(error)]
    return messages[0]


def _menu_version():
    dish_state = Dish.objects.aggregate(count=Count("pk"), latest=Max("updated_at"))
    category_state = Category.objects.aggregate(count=Count("pk"), latest=Max("updated_at"))
    unit_state = Unit.objects.aggregate(count=Count("pk"), latest=Max("updated_at"))
    return "|".join(
        f"{state['count']}:{state['latest'].isoformat() if state['latest'] else '-'}"
        for state in (dish_state, category_state, unit_state)
    )


def _remember_session_id(request, key, object_id):
    values = [str(value) for value in request.session.get(key, []) if str(value).isdigit()]
    value = str(object_id)
    request.session[key] = ([item for item in values if item != value] + [value])[-30:]


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
        expire_qr_check_in_requests()
        orders = _active_qr_orders(token.table)
        context["table"] = token.table
        context["menu_version"] = _menu_version()
        categories = list(customer_categories(with_dishes=True))
        context["categories"] = categories
        # Reuse the prefetched dishes instead of executing the same menu query twice.
        context["dishes"] = [dish for category in categories for dish in category.customer_dishes]
        if token.table.status == token.table.Status.OCCUPIED and len(orders) == 1:
            context["order"] = orders[0]
            context["order_ready"] = True
        else:
            context["order_ready"] = False
            context["can_request_check_in"] = token.table.status in (
                token.table.Status.AVAILABLE,
                token.table.Status.RESERVED,
            )
            request_ids = [
                int(value) for value in self.request.session.get("qr_check_in_request_ids", [])
                if str(value).isdigit()
            ]
            context["check_in_request"] = QRCheckInRequest.objects.filter(
                pk__in=request_ids,
                table_id=token.table_id,
            ).order_by("-created_at", "-pk").first()
            if token.table.status == token.table.Status.RESERVED:
                context["check_in_hint"] = "Bàn đang được giữ cho lịch đặt. Nhân viên sẽ đối chiếu lịch trước khi nhận bàn."
            elif token.table.status == token.table.Status.CLEANING:
                context["check_in_hint"] = "Bàn đang được dọn. Vui lòng chờ nhân viên hoàn tất."
            elif token.table.status == token.table.Status.OCCUPIED:
                context["check_in_hint"] = "Bàn đang đồng bộ đơn phục vụ. Vui lòng gọi nhân viên kiểm tra."
            else:
                context["check_in_hint"] = "Gửi yêu cầu để nhân viên xác nhận và mở bàn. Bạn có thể chọn món trong lúc chờ."
        return context


class CustomerQRCheckInRequestView(View):
    def post(self, request, token):
        try:
            payload = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Dữ liệu nhận bàn không hợp lệ."}, status=400)
        try:
            check_in = create_qr_check_in_request(token=token, guest_count=payload.get("guest_count"))
        except ValidationError as error:
            return JsonResponse({"error": _validation_message(error)}, status=400)
        request_ids = [
            str(value) for value in request.session.get("qr_check_in_request_ids", [])
            if str(value).isdigit()
        ]
        request_ids.append(str(check_in.pk))
        request.session["qr_check_in_request_ids"] = request_ids[-20:]
        return JsonResponse({
            "request_id": check_in.pk,
            "request_code": str(check_in),
            "status": check_in.get_status_display(),
            "expires_at": check_in.expires_at.isoformat(),
        }, status=201)


class CustomerQRTableStateView(View):
    def get(self, request, token):
        qr_token = DiningTableQRToken.objects.select_related("table__area").filter(token=token).first()
        if qr_token is None or not qr_token.is_valid:
            raise Http404("Mã QR không hợp lệ hoặc đã hết hiệu lực.")
        expire_qr_check_in_requests()
        orders = _active_qr_orders(qr_token.table)
        ready = qr_token.table.status == qr_token.table.Status.OCCUPIED and len(orders) == 1
        request_ids = [
            int(value) for value in request.session.get("qr_check_in_request_ids", [])
            if str(value).isdigit()
        ]
        check_in = QRCheckInRequest.objects.filter(
            pk__in=request_ids,
            table_id=qr_token.table_id,
        ).order_by("-created_at", "-pk").first()
        if ready and check_in and check_in.status == QRCheckInRequest.Status.WAITING_CONFIRMATION:
            check_in.status = QRCheckInRequest.Status.CONFIRMED
            check_in.order = orders[0]
            check_in.confirmed_at = timezone.now()
            check_in.save(update_fields=("status", "order", "confirmed_at"))
        return JsonResponse({
            "ready": ready,
            "table_status": qr_token.table.status,
            "menu_version": _menu_version(),
            "request": ({
                "code": str(check_in),
                "status": check_in.status,
                "status_label": check_in.get_status_display(),
                "reject_reason": check_in.reject_reason,
            } if check_in else None),
            "refresh_url": reverse("customer_portal:qr_table", args=[token]),
        })


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
                client_request_id=payload.get("client_request_id"),
            )
        except ValidationError as error:
            return JsonResponse({"error": _validation_message(error)}, status=400)
        _remember_session_id(request, "qr_request_ids", qr_request.pk)
        return JsonResponse({
            "request_id": qr_request.pk,
            "request_code": str(qr_request),
            "status": qr_request.get_status_display(),
            "status_url": reverse("customer_portal:qr_status", args=[token]),
            "duplicate": not getattr(qr_request, "was_created", True),
        }, status=201 if getattr(qr_request, "was_created", True) else 200)


class CustomerQRServiceRequestView(View):
    def post(self, request, token):
        try:
            payload = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Dữ liệu yêu cầu phục vụ không hợp lệ."}, status=400)
        try:
            service_request = create_qr_service_request(
                token=token,
                request_type=payload.get("request_type"),
                note=payload.get("note", ""),
                client_request_id=payload.get("client_request_id"),
            )
        except ValidationError as error:
            return JsonResponse({"error": _validation_message(error)}, status=400)
        _remember_session_id(request, "qr_service_request_ids", service_request.pk)
        return JsonResponse(
            {
                "request_id": service_request.pk,
                "request_code": str(service_request),
                "request_type": service_request.get_request_type_display(),
                "status": service_request.get_status_display(),
                "duplicate": not getattr(service_request, "was_created", True),
                "status_url": reverse("customer_portal:qr_status", args=[token]),
            },
            status=201 if getattr(service_request, "was_created", True) else 200,
        )


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

    def get_service_requests(self, token):
        request_ids = [
            int(value)
            for value in self.request.session.get("qr_service_request_ids", [])
            if str(value).isdigit()
        ]
        return QRServiceRequest.objects.filter(
            pk__in=request_ids,
            table_id=token.table_id,
        ).order_by("-created_at", "-pk")

    @staticmethod
    def serialize_requests(requests):
        return [{
            "code": str(qr_request),
            "status": qr_request.get_status_display(),
            "status_code": qr_request.status,
            "reject_reason": qr_request.reject_reason,
            "created_at": qr_request.created_at.isoformat(),
            "items": [{
                "name": item.dish.name,
                "quantity": item.quantity,
                "status": item.order_item.get_status_display() if item.order_item else qr_request.get_status_display(),
                "status_code": item.order_item.status if item.order_item else qr_request.status,
            } for item in qr_request.items.all()],
        } for qr_request in requests]

    @staticmethod
    def serialize_service_requests(requests):
        return [{
            "code": str(service_request),
            "request_type": service_request.get_request_type_display(),
            "status": service_request.get_status_display(),
            "status_code": service_request.status,
            "note": service_request.note,
            "created_at": service_request.created_at.isoformat(),
        } for service_request in requests]

    def status_payload(self, token):
        return {
            "requests": self.serialize_requests(self.get_requests(token)),
            "service_requests": self.serialize_service_requests(self.get_service_requests(token)),
        }


class CustomerQRStatusView(CustomerQRStatusMixin, TemplateView):
    template_name = "customer/qr_status.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        token = self.get_token()
        context["table"] = token.table
        context["qr_token"] = token
        context["status_data"] = self.status_payload(token)
        context["status_endpoint"] = reverse("customer_portal:qr_status_data", args=[token.token])
        return context


class CustomerQRStatusDataView(CustomerQRStatusMixin, View):
    def get(self, request, token):
        token = self.get_token()
        return conditional_json_response(request, self.status_payload(token))
