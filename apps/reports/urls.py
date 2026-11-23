from django.urls import path

from .views import ReportDashboardView, RevenueExportView, OrderForecastView, AIQualityView, AITransactionsExportView

app_name = "reports"

urlpatterns = [
    path("chat-luong-ai/", AIQualityView.as_view(), name="ai_quality"),
    path("du-lieu-ai.csv", AITransactionsExportView.as_view(), name="ai_transactions"),
    path("", ReportDashboardView.as_view(), name="dashboard"),
    path("du-bao-don/", OrderForecastView.as_view(), name="order_forecast"),
    path("xuat-doanh-thu.csv", RevenueExportView.as_view(), name="export_revenue"),
]
