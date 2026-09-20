from django.urls import path
from . import views

app_name = "customers"
urlpatterns = [
    path("", views.CustomerListView.as_view(), name="customer_list"),
    path("them/", views.CustomerCreateView.as_view(), name="customer_create"),
    path("nhat-ky/", views.CustomerLogListView.as_view(), name="customer_logs"),
    path("<int:pk>/", views.CustomerDetailView.as_view(), name="customer_detail"),
    path("<int:pk>/sua/", views.CustomerUpdateView.as_view(), name="customer_update"),
    path("<int:pk>/xoa/", views.CustomerDeleteView.as_view(), name="customer_delete"),
]
