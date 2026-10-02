"""Trang công khai, tài khoản nội bộ và Django Admin."""

from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from apps.customer_portal.views import CustomerHomeView

from apps.accounts.admin import admin_site

urlpatterns = [
    path("", CustomerHomeView.as_view(), name="home"),
    path("menu/", include("apps.customer_portal.urls")),
    path("reservations/", include("apps.customer_portal.reservation_urls")),
    path("tai-khoan/", include("apps.accounts.urls")),
    path("nhan-vien/", include("apps.employees.urls")),
    path("khach-hang/", include("apps.customers.urls")),
    path("ban/", include("apps.seating.urls")),
    path("dat-ban/", include("apps.bookings.urls")),
    path("thuc-don/", include("apps.menu.urls")),
    path("don-hang/", include("apps.orders.urls")),
    path("sales/", include("apps.orders.sales_urls")),
    path("staff/kitchen/", include("apps.orders.kitchen_urls")),
    path("staff/inventory/", include("apps.inventory.urls")),
    path("bao-cao/", include("apps.reports.urls")),
    path("admin/", admin_site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
