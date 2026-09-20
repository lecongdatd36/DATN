from django.contrib import admin
from django.core.exceptions import PermissionDenied

from apps.accounts.admin import admin_site
from core.permissions import can_manage_accounts

from .models import EmployeeActivityLog, EmployeeProfile, JobPosition


class ReadOnlyPersonnelAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return can_manage_accounts(request.user)

    def has_view_permission(self, request, obj=None):
        return can_manage_accounts(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        return {}

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def save_model(self, request, obj, form, change):
        raise PermissionDenied("Hãy sử dụng màn hình quản lý nhân viên.")

    def delete_model(self, request, obj):
        raise PermissionDenied("Hãy sử dụng màn hình quản lý nhân viên.")


@admin.register(JobPosition, site=admin_site)
class JobPositionAdmin(ReadOnlyPersonnelAdmin):
    list_display = ("code", "name", "group", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "group__name")
    readonly_fields = ("group", "created_at", "updated_at")


@admin.register(EmployeeProfile, site=admin_site)
class EmployeeProfileAdmin(ReadOnlyPersonnelAdmin):
    list_display = ("employee_code", "full_name", "job_position", "employment_status", "phone")
    list_filter = ("job_position", "employment_status")
    search_fields = ("employee_code", "full_name", "phone", "user__username")

    def has_module_permission(self, request):
        return can_manage_accounts(request.user)

    def has_view_permission(self, request, obj=None):
        return can_manage_accounts(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return super().get_readonly_fields(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    def delete_model(self, request, obj):
        raise PermissionDenied("Không được xóa vật lý hồ sơ nhân viên.")


@admin.register(EmployeeActivityLog, site=admin_site)
class EmployeeActivityLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "employee", "action", "performed_by")
    list_filter = ("action",)
    readonly_fields = ("employee", "action", "performed_by", "description", "created_at")

    def has_module_permission(self, request):
        return can_manage_accounts(request.user)

    def has_view_permission(self, request, obj=None):
        return can_manage_accounts(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
