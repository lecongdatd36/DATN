from django.contrib import admin
from django.core.exceptions import PermissionDenied
from apps.accounts.admin import admin_site
from .models import Order, OrderItem, OrderActivityLog
from .permissions import has_order_permission


class ReadOnlyOrderAdmin(admin.ModelAdmin):
    def has_view_permission(self, request, obj=None):
        permission = "view_orderactivitylog" if self.model is OrderActivityLog else "view_order"
        return has_order_permission(request.user, permission)

    def has_module_permission(self, request):
        return self.has_view_permission(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        return {}

    def save_model(self, request, obj, form, change):
        raise PermissionDenied("Hãy sử dụng màn hình Đơn hàng hoặc Bếp.")

    def delete_model(self, request, obj):
        raise PermissionDenied("Đơn hàng và món cần được lưu lịch sử.")

    def delete_queryset(self, request, queryset):
        raise PermissionDenied("Đơn hàng và món cần được lưu lịch sử.")


@admin.register(Order, site=admin_site)
class OrderAdmin(ReadOnlyOrderAdmin):
    list_display = ("order_code", "booking", "status", "created_at")
    list_select_related = ("booking",)
    list_filter = ("status",)


@admin.register(OrderItem, site=admin_site)
class ItemAdmin(ReadOnlyOrderAdmin):
    list_display = ("order", "dish_name", "quantity", "unit_price", "status")
    list_select_related = ("order",)
    list_filter = ("status",)


@admin.register(OrderActivityLog, site=admin_site)
class LogAdmin(ReadOnlyOrderAdmin):
    list_display = ("order", "created_at", "action", "actor_snapshot")
    list_select_related = ("order",)
