from django.urls import path
from . import views

app_name = "orders"
urlpatterns = [
    path("", views.OrderListView.as_view(), name="list"),
    path("mo/", views.OpenOrderView.as_view(), name="open"),
    path("khach-truc-tiep/", views.WalkInView.as_view(), name="walk_in"),
    path("bep/", views.KitchenView.as_view(), name="kitchen"),
    path("<int:pk>/", views.OrderDetailView.as_view(), name="detail"),
    path("<int:pk>/them-mon/", views.OrderActionView.as_view(action="add"), name="add_item"),
    path("<int:pk>/mon/<int:item_id>/sua/", views.OrderActionView.as_view(action="edit"), name="edit_item"),
    path("<int:pk>/mon/<int:item_id>/<str:target>/", views.ItemTransitionView.as_view(), name="transition_item"),
    path("<int:pk>/gui-bep/", views.OrderActionView.as_view(action="send"), name="send"),
    path("<int:pk>/cho-thanh-toan/", views.OrderActionView.as_view(action="await"), name="await"),
    path("<int:pk>/thu-tien/", views.OrderPaymentView.as_view(), name="payment"),
    path("<int:pk>/goi-them/", views.OrderActionView.as_view(action="reopen"), name="reopen"),
    path("<int:pk>/huy/", views.OrderActionView.as_view(action="void"), name="void"),
]
