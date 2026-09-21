from django.contrib import admin
from django.core.exceptions import PermissionDenied
from apps.accounts.admin import admin_site
from .models import Category, Unit, Dish, MenuActivityLog
from .permissions import has_menu_permission


class ReadOnlyMenuAdmin(admin.ModelAdmin):
    def has_view_permission(self, request, obj=None):
        permission = "view_menuactivitylog" if self.model is MenuActivityLog else "manage_menu"
        return has_menu_permission(request.user, permission)

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
        raise PermissionDenied("Hãy sử dụng màn hình Thực đơn.")

    def delete_model(self, request, obj):
        raise PermissionDenied("Hãy ngừng bán tại màn hình Thực đơn.")

    def delete_queryset(self, request, queryset):
        raise PermissionDenied("Hãy ngừng bán tại màn hình Thực đơn.")


@admin.register(Category, Unit, site=admin_site)
class CatalogAdmin(ReadOnlyMenuAdmin):
    list_display = ("name", "is_active")
    search_fields = ("name",)


@admin.register(Dish, site=admin_site)
class DishAdmin(ReadOnlyMenuAdmin):
    list_display = ("code", "name", "category", "unit", "price", "status")
    list_select_related = ("category", "unit")
    search_fields = ("code", "name")
    list_filter = ("status", "category")


@admin.register(MenuActivityLog, site=admin_site)
class MenuLogAdmin(ReadOnlyMenuAdmin):
    list_display = ("created_at", "entity", "label_snapshot", "action", "actor_snapshot")
    search_fields = ("label_snapshot", "actor_snapshot")
