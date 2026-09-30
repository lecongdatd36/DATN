from django.contrib import admin

from apps.accounts.admin import admin_site
from .models import Ingredient, InventoryTransaction, Supplier


@admin.register(Ingredient, site=admin_site)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "unit", "stock_quantity", "low_stock_threshold", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(Supplier, site=admin_site)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "phone")


@admin.register(InventoryTransaction, site=admin_site)
class InventoryTransactionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "transaction_type", "ingredient", "quantity", "stock_before", "stock_after", "performed_by")
    list_filter = ("transaction_type",)
    readonly_fields = ("ingredient", "transaction_type", "quantity", "stock_before", "stock_after", "unit_cost", "supplier", "note", "performed_by", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
