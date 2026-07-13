# config/urls.py
from django.urls import path, include
urlpatterns = [path('api/rpc/', include('rpc.urls'))]

# rpc/urls.py
from django.urls import path
from .views import RPCView
urlpatterns = [path('<int:sp_id>/', RPCView.as_view(), name='rpc')]