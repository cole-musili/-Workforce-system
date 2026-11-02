from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

from apps.core import views as core_views


urlpatterns = [
    path("admin/", admin.site.urls),

    path(
        "accounts/login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html"
        ),
        name="login",
    ),

    path(
        "accounts/logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),

    path("", core_views.dashboard, name="dashboard"),
    path("accounts/", include("apps.core.urls")),

    path("employees/", include("apps.employees.urls")),
    path("imports/", include("apps.imports.urls")),
    path("duplicates/", include("apps.duplicates.urls")),
    path("analytics/", include("apps.analytics.urls")),
    path("reports/", include("apps.reports.urls")),
]
