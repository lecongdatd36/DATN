from django.urls import path
from . import zalopay_views as views

app_name = "zalopay"
urlpatterns = [
    path("create/", views.create, name="create"),
    path("deposit/<uuid:token>/", views.deposit_create, name="deposit_create"),
    path("callback/", views.callback, name="callback"),
    path("result/<uuid:token>/", views.result, name="result"),
    path("status/<uuid:token>/", views.state, name="state"),
    path("query/<uuid:token>/", views.query, name="query"),
]
