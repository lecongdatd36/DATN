from django.urls import path

from apps.bookings.views import (
    PublicReservationCreateView, PublicReservationLookupView,
    PublicReservationStatusView, PublicReservationSuccessView,
    PublicTableCheckView,
)

app_name = "customer_reservations"

urlpatterns = [
    path("check/", PublicTableCheckView.as_view(), name="check"),
    path("create/", PublicReservationCreateView.as_view(), name="create"),
    path("success/", PublicReservationSuccessView.as_view(), name="success"),
    path("lookup/", PublicReservationLookupView.as_view(), name="lookup"),
    path("status/<int:pk>/", PublicReservationStatusView.as_view(), name="status"),
]