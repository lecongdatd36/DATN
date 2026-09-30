from django.urls import path
from . import views

app_name = "customers"
urlpatterns = [
    path("", views.CustomerListView.as_view(), name="customer_list"),
    path("hang-thanh-vien/", views.MembershipTierListView.as_view(), name="membership_tier_list"),
    path("hang-thanh-vien/them/", views.MembershipTierCreateView.as_view(), name="membership_tier_create"),
    path("hang-thanh-vien/<int:pk>/sua/", views.MembershipTierUpdateView.as_view(), name="membership_tier_update"),
    path("them/", views.CustomerCreateView.as_view(), name="customer_create"),
    path("nhat-ky/", views.CustomerLogListView.as_view(), name="customer_logs"),
    path("<int:pk>/", views.CustomerDetailView.as_view(), name="customer_detail"),
    path("<int:pk>/sua/", views.CustomerUpdateView.as_view(), name="customer_update"),
    path("<int:pk>/xoa/", views.CustomerDeleteView.as_view(), name="customer_delete"),
]
