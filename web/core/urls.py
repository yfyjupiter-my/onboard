from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.checklist, name="home"),
    path("material/<int:pk>/", views.material_view, name="material"),
    path("material/<int:pk>/quiz/", views.quiz, name="quiz"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
