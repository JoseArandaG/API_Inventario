from django.urls import path
from .views import RPCView

urlpatterns = [path('<int:sp_id>/', RPCView.as_view(), name='rpc')]
