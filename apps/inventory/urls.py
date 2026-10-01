from django.urls import path

from .views import (
    IngredientFormView, InventoryWorkspaceView, PurchaseReceiptDetailView, PurchaseReceiptListView,
    RecipeView, StocktakeDetailView, StocktakeListView, SupplierFormView, WasteRecordView,
)

app_name = "inventory"
urlpatterns = [
    path("", InventoryWorkspaceView.as_view(), name="workspace"),
    path("nguyen-lieu/them/", IngredientFormView.as_view(), name="ingredient_create"),
    path("nguyen-lieu/<int:pk>/sua/", IngredientFormView.as_view(), name="ingredient_update"),
    path("nha-cung-cap/them/", SupplierFormView.as_view(), name="supplier_create"),
    path("nha-cung-cap/<int:pk>/sua/", SupplierFormView.as_view(), name="supplier_update"),
    path("nhap-hang/", PurchaseReceiptListView.as_view(), name="purchase_list"),
    path("nhap-hang/<int:pk>/", PurchaseReceiptDetailView.as_view(), name="purchase_detail"),
    path("kiem-ke/", StocktakeListView.as_view(), name="stocktake_list"),
    path("kiem-ke/<int:pk>/", StocktakeDetailView.as_view(), name="stocktake_detail"),
    path("hao-hut/", WasteRecordView.as_view(), name="waste"),
    path("cong-thuc/<int:dish_id>/", RecipeView.as_view(), name="recipe"),
]
