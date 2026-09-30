from django.urls import path

from .views import InventoryWorkspaceView

app_name = "inventory"
urlpatterns = [path("", InventoryWorkspaceView.as_view(), name="workspace")]
