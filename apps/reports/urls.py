from django.urls import path

from .views import ReportDashboardView, RevenueExportView

app_name = "reports"

urlpatterns = [
    path("", ReportDashboardView.as_view(), name="dashboard"),
    path("xuat-doanh-thu.csv", RevenueExportView.as_view(), name="export_revenue"),
]
