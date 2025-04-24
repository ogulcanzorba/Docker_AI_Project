from django.urls import path
from . import views
from .views import custom_logout

urlpatterns = [
    path('', views.login_page, name='login'),  # Root URL shows login page
    path('lectures/', views.lecture_list, name='lecture_list'),  # Lecture list
    path('logout/', custom_logout, name='logout'),
    path('signup/', views.signup, name='signup'),
    path('lecture/<str:lecture_name>/', views.lecture_view, name='lecture'),
]