from django.urls import path
from . import views
from .views import custom_logout

urlpatterns = [
    path('', views.login_page, name='login'),
    path('lectures/', views.lecture_list, name='lecture_list'),
    path('logout/', custom_logout, name='logout'),
    path('signup/', views.signup, name='signup'),
    path('lecture/<str:lecture_name>/', views.lecture_view, name='lecture'),
    path('lecture/<str:lecture_name>/stream/', views.stream_lecture_response, name='stream_lecture_response'),
    path('lecture/<str:lecture_name>/quiz/', views.generate_quiz_view, name='generate_quiz'),
    path('lecture/<str:lecture_name>/upload/', views.upload_lecture_pdf, name='upload_lecture_pdf'),
    path('upload/', views.upload_lecture_pdf, name='upload_lecture_pdf_generic'),  # New generic upload URL
    path('transcript/<int:transcript_id>/', views.transcript_detail, name='transcript_detail'),
    path('task/<str:task_id>/', views.task_status, name='task_status'),  # Added for Celery
]