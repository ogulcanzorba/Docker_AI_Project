from django.urls import path
from . import views

urlpatterns = [
    path('', views.lecture_list, name='lecture_list'),
    path('login/', views.login_page, name='login'),
    path('signup/', views.signup, name='signup'),
    path('logout/', views.custom_logout, name='logout'),
    path('lecture/<str:lecture_name>/', views.lecture_view, name='lecture'),
    path('quiz/<str:lecture_name>/', views.generate_quiz_view, name='generate_quiz'),
    path('quiz/<str:lecture_name>/retry/', views.retry_quiz, name='retry_quiz'),
    path('quiz-answer/<int:quiz_id>/', views.submit_quiz_answer, name='submit_quiz_answer'),
    path('upload/<str:lecture_name>/', views.upload_lecture_pdf, name='upload_lecture_pdf'),
    path('transcript/<int:transcript_id>/', views.transcript_detail, name='transcript_detail'),
    path('task/<str:task_id>/', views.task_status, name='task_status'),
    path('save_chat/<str:lecture_name>/', views.save_chat, name='save_chat'),
]