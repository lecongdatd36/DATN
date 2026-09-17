"""Các vai trò truy cập hệ thống, độc lập với chức vụ nghiệp vụ."""

from django.db import models


class SystemRole(models.TextChoices):
    MANAGER = "MANAGER", "Quản trị viên / Quản lý"
    EMPLOYEE = "EMPLOYEE", "Nhân viên"
