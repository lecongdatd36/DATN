"""Các URL thuộc module tài khoản."""

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("dang-nhap/", views.LoginView.as_view(), name="login"),
    path("dang-xuat/", views.LogoutView.as_view(), name="logout"),
    path("", views.WorkspaceView.as_view(), name="workspace"),
    path("doi-mat-khau/", views.PasswordChangeView.as_view(), name="password_change"),
    path("doi-mat-khau/hoan-tat/", views.PasswordChangeDoneView.as_view(), name="password_change_done"),
    path("quan-ly/", views.AccountListView.as_view(), name="account_list"),
    path("quan-ly/tao-moi/", views.AccountCreateView.as_view(), name="account_create"),
    path("quan-ly/<int:pk>/", views.AccountDetailView.as_view(), name="account_detail"),
    path("quan-ly/<int:pk>/chinh-sua/", views.AccountUpdateView.as_view(), name="account_update"),
    path("quan-ly/<int:pk>/khoa/", views.AccountStatusView.as_view(), name="account_lock"),
    path("quan-ly/<int:pk>/mo-khoa/", views.AccountStatusView.as_view(activate=True), name="account_unlock"),
    path("quan-ly/<int:pk>/dat-lai-mat-khau/", views.EmployeePasswordResetView.as_view(), name="password_reset"),
]
