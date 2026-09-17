from django.contrib import admin
from django.core.exceptions import PermissionDenied

from apps.accounts.admin import admin_site

from .models import EmployeeActivityLog, EmployeeProfile


@admin.register(EmployeeProfile, site=admin_site)
class EmployeeProfileAdmin(admin.ModelAdmin):
    list_display = ("employee_code", "full_name", "job_position", "employment_status", "phone")
    list_filter = ("job_position", "employment_status")
    search_fields = ("employee_code", "full_name", "phone", "user__username")

    def has_delete_permission(self, request, obj=None):
        return False

    def delete_model(self, request, obj):
        raise PermissionDenied("Không được xóa vật lý hồ sơ nhân viên.")


@admin.register(EmployeeActivityLog, site=admin_site)
class EmployeeActivityLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "employee", "action", "performed_by")
    list_filter = ("action",)
    readonly_fields = ("employee", "action", "performed_by", "description", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
