from django.urls import path

from . import views

app_name = "employees"

urlpatterns = [
    path("", views.EmployeeListView.as_view(), name="employee_list"),
    path("tao-moi/", views.EmployeeCreateView.as_view(), name="employee_create"),
    path("<int:pk>/", views.EmployeeDetailView.as_view(), name="employee_detail"),
    path("<int:pk>/chinh-sua/", views.EmployeeUpdateView.as_view(), name="employee_update"),
    path("<int:pk>/trang-thai/", views.EmployeeStatusView.as_view(), name="employee_status"),
]
