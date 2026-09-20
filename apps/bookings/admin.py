from django.contrib import admin
from django.core.exceptions import PermissionDenied
from apps.accounts.admin import admin_site
from .models import Booking, BookingActivityLog
from .permissions import has_booking_permission


class ReadOnlyBookingAdmin(admin.ModelAdmin):
    def has_view_permission(self, request, obj=None):
        return has_booking_permission(request.user, f"view_{self.opts.model_name}")

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
        raise PermissionDenied("Hãy thao tác tại màn hình Đặt bàn.")

    def delete_model(self, request, obj):
        raise PermissionDenied("Hãy hủy lịch tại màn hình Đặt bàn.")

    def delete_queryset(self, request, queryset):
        raise PermissionDenied("Hãy hủy lịch tại màn hình Đặt bàn.")


@admin.register(Booking, site=admin_site)
class BookingAdmin(ReadOnlyBookingAdmin):
    list_display = ("booking_code", "customer_name", "customer_phone", "table", "starts_at", "ends_at", "status")
    search_fields = ("customer_name", "customer_phone", "table__code")
    list_filter = ("status",)
    list_select_related = ("table",)


@admin.register(BookingActivityLog, site=admin_site)
class BookingLogAdmin(ReadOnlyBookingAdmin):
    list_display = ("created_at", "booking", "action", "actor_snapshot")
    list_select_related = ("booking",)
    search_fields = ("actor_snapshot", "description")
