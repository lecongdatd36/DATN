from django.contrib import admin

from apps.accounts.admin import admin_site
from .models import (
    Ingredient, InventoryTransaction, PurchaseReceipt, PurchaseReceiptLine,
    RecipeIngredient, Stocktake, StocktakeLine, Supplier, WasteRecord,
)


@admin.register(Ingredient, site=admin_site)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "unit", "stock_quantity", "average_unit_cost", "low_stock_threshold", "is_active")
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
    readonly_fields = ("ingredient", "transaction_type", "quantity", "stock_before", "stock_after", "unit_cost", "supplier", "note", "performed_by", "order_item_reference", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RecipeIngredient, site=admin_site)
class RecipeIngredientAdmin(admin.ModelAdmin):
    list_display = ("dish", "ingredient", "quantity", "updated_at")
    list_select_related = ("dish", "ingredient")
    search_fields = ("dish__code", "dish__name", "ingredient__code", "ingredient__name")


class PurchaseReceiptLineInline(admin.TabularInline):
    model = PurchaseReceiptLine
    extra = 0
    readonly_fields = ("ingredient", "quantity", "unit_cost")


@admin.register(PurchaseReceipt, site=admin_site)
class PurchaseReceiptAdmin(admin.ModelAdmin):
    list_display = ("receipt_code", "supplier", "status", "received_at")
    list_filter = ("status",)
    inlines = (PurchaseReceiptLineInline,)


class StocktakeLineInline(admin.TabularInline):
    model = StocktakeLine
    extra = 0
    readonly_fields = ("ingredient", "system_quantity", "actual_quantity")


@admin.register(Stocktake, site=admin_site)
class StocktakeAdmin(admin.ModelAdmin):
    list_display = ("stocktake_code", "status", "created_at", "posted_at")
    list_filter = ("status",)
    inlines = (StocktakeLineInline,)


@admin.register(WasteRecord, site=admin_site)
class WasteRecordAdmin(admin.ModelAdmin):
    list_display = ("waste_code", "ingredient", "quantity", "reason", "total_cost", "created_at")
    list_filter = ("reason",)
