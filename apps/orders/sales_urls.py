from django.urls import path

from .sales_views import CustomerLookupView, EstimatePrintView, FinishCleaningView, InvoicePrintView, PaymentActionView, SalesActionView, SalesStateView, SalesWorkspaceView

app_name = "sales"
urlpatterns = [
    path("", SalesWorkspaceView.as_view(), name="workspace"),
    path("state/", SalesStateView.as_view(), name="state"),
    path("customers/lookup/", CustomerLookupView.as_view(), name="customer_lookup"),
    path("orders/<int:order_id>/estimate/", EstimatePrintView.as_view(), name="estimate_print"),
    path("invoices/<int:invoice_id>/print/", InvoicePrintView.as_view(), name="invoice_print"),
    path("action/<str:action>/", SalesActionView.as_view(), name="action"),
    path("payment/", PaymentActionView.as_view(), name="payment"),
    path("table/<int:table_id>/finish-cleaning/", FinishCleaningView.as_view(), name="finish_cleaning"),
]
