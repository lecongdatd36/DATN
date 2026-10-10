from django.urls import path

from .kitchen_views import KitchenStateView, KitchenStreamView, KitchenTransitionView, KitchenWorkspaceView

app_name = "kitchen"
urlpatterns = [
    path("", KitchenWorkspaceView.as_view(), name="workspace"),
    path("state/", KitchenStateView.as_view(), name="state"),
    path("stream/", KitchenStreamView.as_view(), name="stream"),
    path("item/<int:item_id>/<str:target>/", KitchenTransitionView.as_view(), name="transition"),
]
