from django.contrib import admin
from django.core.exceptions import PermissionDenied

from apps.accounts.admin import admin_site
from .models import Customer, CustomerActivityLog, MembershipTier
from .permissions import has_customer_permission


class ReadOnlyCustomerAdmin(admin.ModelAdmin):
    def has_view_permission(self, request, obj=None):
        return has_customer_permission(request.user, f"view_{self.opts.model_name}")

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
        raise PermissionDenied("Hãy thao tác tại màn hình Khách hàng.")

    def delete_model(self, request, obj):
        raise PermissionDenied("Hãy thao tác tại màn hình Khách hàng.")

    def delete_queryset(self, request, queryset):
        raise PermissionDenied("Hãy thao tác tại màn hình Khách hàng.")


@admin.register(Customer, site=admin_site)
class CustomerAdmin(ReadOnlyCustomerAdmin):
    list_display = ("customer_code", "full_name", "phone", "created_at")
    search_fields = ("full_name", "phone")
    readonly_fields = ("customer_code", "full_name", "phone", "created_at", "updated_at")
    fields = readonly_fields


@admin.register(CustomerActivityLog, site=admin_site)
class CustomerActivityLogAdmin(ReadOnlyCustomerAdmin):
    list_display = ("created_at", "customer_code_snapshot", "customer_name_snapshot", "action", "performed_by_name_snapshot")
    list_filter = ("action",)
    search_fields = ("customer_code_snapshot", "customer_name_snapshot", "performed_by_name_snapshot")
    readonly_fields = ("created_at", "customer_code_snapshot", "customer_name_snapshot", "action", "performed_by_name_snapshot", "description")
    fields = readonly_fields


@admin.register(MembershipTier, site=admin_site)
class MembershipTierAdmin(admin.ModelAdmin):
    list_display = ("name", "minimum_spending", "discount_percent", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
