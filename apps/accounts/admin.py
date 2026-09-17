from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.admin.models import LogEntry
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.forms import UserChangeAdminForm, UserCreationAdminForm
from apps.accounts.models import User
from core.permissions import can_access_admin


class RoleAwareAdminAuthenticationForm(AdminAuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not can_access_admin(user):
            raise ValidationError(
                self.error_messages["invalid_login"],
                code="invalid_login",
                params={"username": self.username_field.verbose_name},
            )


class RoleAwareAdminSite(AdminSite):
    site_header = "Quản trị QLNH"
    site_title = "Quản trị QLNH"
    index_title = "Quản trị hệ thống"
    login_form = RoleAwareAdminAuthenticationForm

    def has_permission(self, request):
        return can_access_admin(request.user)


admin_site = RoleAwareAdminSite(name="admin")


@admin.register(User, site=admin_site)
class CustomUserAdmin(UserAdmin):
    form = UserChangeAdminForm
    add_form = UserCreationAdminForm
    list_display = ("username", "email", "role", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("username", "pk")
    readonly_fields = ("last_login", "date_joined", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Thông tin cá nhân", {"fields": ("first_name", "last_name", "email")}),
        (
            "Vai trò và quyền truy cập",
            {
                "fields": (
                    "role", "is_active", "is_staff", "is_superuser",
                    "groups", "user_permissions",
                )
            },
        ),
        (
            "Thời gian",
            {"fields": ("last_login", "date_joined", "created_at", "updated_at")},
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username", "email", "first_name", "last_name",
                    "password1", "password2", "role", "is_active", "is_staff",
                ),
            },
        ),
    )

    def _can_write_users(self, request):
        return can_access_admin(request.user) and request.user.is_superuser

    def has_module_permission(self, request):
        return self._can_write_users(request)

    def has_view_permission(self, request, obj=None):
        return self._can_write_users(request)

    def has_add_permission(self, request):
        return self._can_write_users(request)

    def has_change_permission(self, request, obj=None):
        # Quản lý thường dùng UI dịch vụ; không thể cấp thêm quyền qua admin.
        return self._can_write_users(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if not self._can_write_users(request):
            raise PermissionDenied("Chỉ superuser được chỉnh sửa tài khoản tại đây.")
        if change:
            current_user = User.objects.select_for_update().get(pk=obj.pk)
            obj.session_version = current_user.session_version
            if not obj.is_active:
                obj.session_version += 1
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        raise PermissionDenied("Tài khoản chỉ được khóa, không được xóa.")

    def delete_queryset(self, request, queryset):
        raise PermissionDenied("Tài khoản chỉ được khóa, không được xóa.")


@admin.register(LogEntry, site=admin_site)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("action_time", "user", "object_repr", "change_message")
    list_filter = ("action_flag", "content_type")
    search_fields = ("user__username", "object_repr", "change_message")
    ordering = ("-action_time", "-pk")
    date_hierarchy = "action_time"
    readonly_fields = (
        "action_time", "user", "content_type", "object_id", "object_repr",
        "action_flag", "change_message",
    )
    fields = readonly_fields

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "content_type")

    def has_module_permission(self, request):
        return can_access_admin(request.user)

    def has_view_permission(self, request, obj=None):
        return can_access_admin(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        return {}

    def save_model(self, request, obj, form, change):
        raise PermissionDenied("Nhật ký thao tác chỉ được xem.")

    def delete_model(self, request, obj):
        raise PermissionDenied("Nhật ký thao tác chỉ được xem.")

    def delete_queryset(self, request, queryset):
        raise PermissionDenied("Nhật ký thao tác chỉ được xem.")
