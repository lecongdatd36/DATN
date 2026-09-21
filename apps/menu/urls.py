from django.urls import path
from . import views

app_name = "menu"
urlpatterns = [
    path("", views.DishListView.as_view(), name="dish_list"),
    path("them/", views.DishFormView.as_view(), name="dish_create"),
    path("nhom-mon/", views.CatalogListView.as_view(), name="category_list"),
    path("nhom-mon/them/", views.CatalogFormView.as_view(), name="category_create"),
    path("nhom-mon/<int:pk>/sua/", views.CatalogFormView.as_view(), name="category_update"),
    path("don-vi/", views.UnitListView.as_view(), name="unit_list"),
    path("don-vi/them/", views.UnitFormView.as_view(), name="unit_create"),
    path("don-vi/<int:pk>/sua/", views.UnitFormView.as_view(), name="unit_update"),
    path("nhat-ky/", views.MenuLogView.as_view(), name="logs"),
    path("<int:pk>/", views.DishDetailView.as_view(), name="detail"),
    path("<int:pk>/sua/", views.DishFormView.as_view(), name="dish_update"),
    path("<int:pk>/con-het/", views.AvailabilityView.as_view(), name="availability"),
]
