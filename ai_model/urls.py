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
]