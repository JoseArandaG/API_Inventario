from django.urls import path, include

urlpatterns = [
    path('rpc/', include('rpc.urls')),
]