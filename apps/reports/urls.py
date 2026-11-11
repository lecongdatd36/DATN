from django.urls import path

from .views import ReportDashboardView, RevenueExportView, OrderForecastView

app_name = "reports"

urlpatterns = [
    path("", ReportDashboardView.as_view(), name="dashboard"),
    path("du-bao-don/", OrderForecastView.as_view(), name="order_forecast"),
    path("xuat-doanh-thu.csv", RevenueExportView.as_view(), name="export_revenue"),
]
