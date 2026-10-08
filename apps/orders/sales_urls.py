from django.urls import path

from .sales_views import CustomerLookupView, EstimatePrintView, FinishCleaningView, InvoicePrintView, PaymentActionView, PromotionActionView, PromotionCreateView, PromotionListView, PromotionUpdateView, QRCheckInActionView, QRRequestActionView, QRServiceRequestActionView, SalesActionView, SalesStateView, SalesWorkspaceView, VnpayIpnView, VnpayReturnView

app_name = "sales"
urlpatterns = [
    path("", SalesWorkspaceView.as_view(), name="workspace"),
    path("state/", SalesStateView.as_view(), name="state"),
    path("qr-check-ins/<int:request_id>/<str:action>/", QRCheckInActionView.as_view(), name="qr_check_in_action"),
    path("qr-requests/<int:request_id>/<str:action>/", QRRequestActionView.as_view(), name="qr_request_action"),
    path("qr-service-requests/<int:request_id>/complete/", QRServiceRequestActionView.as_view(), name="qr_service_request_action"),
    path("customers/lookup/", CustomerLookupView.as_view(), name="customer_lookup"),
    path("orders/<int:order_id>/estimate/", EstimatePrintView.as_view(), name="estimate_print"),
    path("invoices/<int:invoice_id>/print/", InvoicePrintView.as_view(), name="invoice_print"),
    path("action/<str:action>/", SalesActionView.as_view(), name="action"),
    path("payment/", PaymentActionView.as_view(), name="payment"),
    path("payment/promotion/", PromotionActionView.as_view(), name="apply_promotion"),
    path("payment/vnpay/ipn/", VnpayIpnView.as_view(), name="vnpay_ipn"),
    path("payment/vnpay/return/", VnpayReturnView.as_view(), name="vnpay_return"),
    path("table/<int:table_id>/finish-cleaning/", FinishCleaningView.as_view(), name="finish_cleaning"),
    path("promotions/", PromotionListView.as_view(), name="promotion_list"),
    path("promotions/new/", PromotionCreateView.as_view(), name="promotion_create"),
    path("promotions/<int:pk>/edit/", PromotionUpdateView.as_view(), name="promotion_update"),
]
