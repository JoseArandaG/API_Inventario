from django.urls import path
from .views import procesar_voz_api, historial_voz_api

urlpatterns = [
    path('procesar/', procesar_voz_api, name='api_procesar_voz'),
    path('historial/', historial_voz_api, name='api_historial_voz'),
]