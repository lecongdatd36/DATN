from django.urls import path
from . import views

app_name = "bookings"
urlpatterns = [
    path("", views.BookingListView.as_view(), name="list"),
    path("them/", views.BookingFormView.as_view(), name="create"),
    path("cau-hinh/", views.BookingSettingsView.as_view(), name="settings"),
    path("ban-phu-hop/", views.AvailabilityView.as_view(), name="availability"),
    path("<int:pk>/", views.BookingDetailView.as_view(), name="detail"),
    path("<int:pk>/sua/", views.BookingFormView.as_view(), name="update"),
    path("<int:pk>/trang-thai/<str:target>/", views.BookingTransitionView.as_view(), name="transition"),
]
