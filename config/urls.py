from django.urls import path, include

urlpatterns = [
    path('api/rpc/', include('rpc.urls')),
    path('api/voice/', include('voice_control.urls')),
]
