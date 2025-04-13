from django.urls import path
from . import views
from django.contrib.auth.views import LogoutView
from .views import custom_logout

urlpatterns = [
    path('', views.login_page, name='login_page'),  # Homepage = login
    path('chat/', views.index, name='chat'),
    path('login/', views.login_page, name='login'),  # Optional alias
    path('logout/', custom_logout, name='logout'),
    path('signup/', views.signup, name='signup'),
]
