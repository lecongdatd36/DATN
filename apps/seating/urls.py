from django.urls import path
from . import views

app_name = "seating"
urlpatterns = [
    path("", views.TableListView.as_view(), name="table_list"),
    path("them/", views.TableFormView.as_view(), name="table_create"),
    path("<int:pk>/sua/", views.TableFormView.as_view(), name="table_update"),
    path("khu-vuc/", views.AreaListView.as_view(), name="area_list"),
    path("khu-vuc/them/", views.AreaFormView.as_view(), name="area_create"),
    path("khu-vuc/<int:pk>/sua/", views.AreaFormView.as_view(), name="area_update"),
    path("nhat-ky/", views.SeatingLogView.as_view(), name="logs"),
]
