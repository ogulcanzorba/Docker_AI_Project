from django.urls import path
from .views import index, generate_ai_response

urlpatterns = [
    path('', index, name='index'),
    path('ai/generate/', generate_ai_response, name='generate_ai_response'),
]
