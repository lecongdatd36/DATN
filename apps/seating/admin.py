from django.contrib import admin
from django.core.exceptions import PermissionDenied
from apps.accounts.admin import admin_site
from .models import Area, DiningTable, SeatingActivityLog
from .permissions import has_seating_permission


class ReadOnlySeatingAdmin(admin.ModelAdmin):
    def has_view_permission(self, request, obj=None):
        return has_seating_permission(request.user, f"view_{self.opts.model_name}")

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
        raise PermissionDenied("Hãy sử dụng màn hình Khu vực và Bàn.")

    def delete_model(self, request, obj):
        raise PermissionDenied("Hãy ngừng sử dụng tại màn hình Khu vực và Bàn.")

    def delete_queryset(self, request, queryset):
        raise PermissionDenied("Hãy ngừng sử dụng tại màn hình Khu vực và Bàn.")


@admin.register(Area, site=admin_site)
class AreaAdmin(ReadOnlySeatingAdmin):
    list_display = ("name", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active",)


@admin.register(DiningTable, site=admin_site)
class TableAdmin(ReadOnlySeatingAdmin):
    list_display = ("code", "area", "capacity", "is_active")
    list_select_related = ("area",)
    search_fields = ("code", "area__name")
    list_filter = ("area", "is_active")


@admin.register(SeatingActivityLog, site=admin_site)
class SeatingLogAdmin(ReadOnlySeatingAdmin):
    list_display = ("created_at", "entity", "label_snapshot", "action", "actor_snapshot")
    search_fields = ("label_snapshot", "actor_snapshot")
    list_filter = ("entity", "action")
