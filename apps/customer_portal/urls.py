from django.urls import path

from . import views

app_name = "customer_portal"

urlpatterns = [
    path("", views.CustomerMenuView.as_view(), name="menu"),
    path("table/<uuid:token>/check-in/", views.CustomerQRCheckInRequestView.as_view(), name="qr_check_in"),
    path("table/<uuid:token>/state/data/", views.CustomerQRTableStateView.as_view(), name="qr_table_state"),
    path("table/<uuid:token>/request/", views.CustomerQRRequestView.as_view(), name="qr_request"),
    path("table/<uuid:token>/service-request/", views.CustomerQRServiceRequestView.as_view(), name="qr_service_request"),
    path("table/<uuid:token>/status/data/", views.CustomerQRStatusDataView.as_view(), name="qr_status_data"),
    path("table/<uuid:token>/status/", views.CustomerQRStatusView.as_view(), name="qr_status"),
    path("table/<uuid:token>/", views.CustomerQRTableView.as_view(), name="qr_table"),
    path("<int:pk>/", views.CustomerDishDetailView.as_view(), name="dish_detail"),
]
