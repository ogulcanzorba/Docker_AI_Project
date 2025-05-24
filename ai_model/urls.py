from django.urls import path
from ai_model import views

urlpatterns = [
    path('', views.lecture_list, name='lecture_list'),
    path('lecture/<str:lecture_name>/', views.lecture_view, name='lecture'),
    path('generate_quiz/<str:lecture_name>/', views.generate_quiz_view, name='generate_quiz'),
    path('upload_lecture_pdf/<str:lecture_name>/', views.upload_lecture_pdf, name='upload_lecture_pdf'),
    path('transcript/<int:transcript_id>/', views.transcript_detail, name='transcript_detail'),
    path('login/', views.login_page, name='login'),
    path('signup/', views.signup, name='signup'),
    path('logout/', views.custom_logout, name='logout'),
    path('task/<str:task_id>/', views.task_status, name='task_status'),
    path('save_chat/<str:lecture_name>/', views.save_chat, name='save_chat'),
]