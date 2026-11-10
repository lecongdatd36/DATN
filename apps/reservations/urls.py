from django.urls import path
from . import views

app_name="online_reservations"
urlpatterns=[
    path("",views.create,name="create"),
    path("dat-mon-truoc-khong/",views.preorder_choice,name="choice"),
    path("dat-ban/",views.booking_details,{"flow":"table"},name="table"),
    path("dat-mon-truoc/",views.booking_details,{"flow":"preorder"},name="preorder"),
    path("chon-mon/",views.menu,name="menu"),
    path("xac-nhan/",views.review,name="review"),
    path("tra-cuu/",views.lookup,name="lookup"),
    path("chi-tiet/<uuid:token>/",views.detail,name="detail"),
    path("chi-tiet/<uuid:token>/state/",views.state,name="state"),
    path("vnpay/ipn/",views.ipn,name="ipn"),
    path("vnpay/return/",views.payment_return,name="payment_return"),
    path("quan-ly/",views.manage,name="manage"),
    path("quan-ly/<int:pk>/",views.manage_detail,name="manage_detail"),
    path("bep/",views.kitchen,name="kitchen"),
    path("chinh-sach/",views.policy,name="policy"),
]
