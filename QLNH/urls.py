"""Trang công khai, tài khoản nội bộ và Django Admin."""

from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.views.generic import TemplateView

from apps.accounts.admin import admin_site

urlpatterns = [
    path("", TemplateView.as_view(template_name="home.html"), name="home"),
    path("tai-khoan/", include("apps.accounts.urls")),
    path("nhan-vien/", include("apps.employees.urls")),
    path("khach-hang/", include("apps.customers.urls")),
    path("ban/", include("apps.seating.urls")),
    path("dat-ban/", include("apps.bookings.urls")),
    path("thuc-don/", include("apps.menu.urls")),
    path("don-hang/", include("apps.orders.urls")),
    path("admin/", admin_site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
