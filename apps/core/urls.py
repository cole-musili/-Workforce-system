from django.urls import path

from . import views

urlpatterns = [
    path("profile/", views.profile, name="profile"),
    path("profile/password/", views.change_password, name="change_password"),
    path("users/", views.user_management, name="user_management"),
    path(
        "users/<int:user_id>/toggle-active/",
        views.toggle_user_active,
        name="toggle_user_active",
    ),
    path(
        "users/<int:user_id>/reset-password/",
        views.reset_user_password,
        name="reset_user_password",
    ),
]
