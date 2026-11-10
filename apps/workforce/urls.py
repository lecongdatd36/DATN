from django.urls import path
from . import views

app_name = "workforce"
urlpatterns = [
    path("", views.schedules, name="schedules"),
    path("diem-cham-cong/", views.point, name="point"),
    path("diem-cham-cong/api/", views.point_api, name="point_api"),
    path("ca-lam/", views.shifts, name="shifts"),
    path("ca-lam/<int:pk>/", views.shifts, name="shift_edit"),
    path("lich/<int:pk>/", views.schedule_action, name="schedule_action"),
    path("lich-cua-toi/", views.mine, name="mine"),
    path("bang-cong/", views.timesheet, name="timesheet"),
    path("bang-cong/<int:pk>/", views.attendance_detail, name="attendance"),
    path("khuon-mat/", views.faces, name="faces"),
    path("khuon-mat/<int:pk>/", views.faces, name="face_enroll"),
    path("khuon-mat/<int:pk>/luu/", views.face_save, name="face_save"),
    path("khuon-mat/<int:pk>/xoa/", views.face_delete, name="face_delete"),
    path("thiet-bi/", views.devices, name="devices"),
    path("thiet-bi/<int:pk>/thu-hoi/", views.device_revoke, name="device_revoke"),
    path("kiosk/", views.kiosk, name="kiosk"),
    path("kiosk/api/", views.kiosk_api, name="kiosk_api"),
]
