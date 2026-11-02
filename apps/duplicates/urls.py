
from django.urls import path

from apps.duplicates import views

app_name = "duplicates"

urlpatterns = [
    path(
        "",
        views.duplicate_dashboard,
        name="dashboard",
    ),

    path(
        "groups/",
        views.duplicate_group_list,
        name="group_list",
    ),

    path(
        "groups/<int:pk>/",
        views.duplicate_group_detail,
        name="group_detail",
    ),

    path(
        "groups/<int:pk>/resolve/",
        views.resolve_duplicate_group,
        name="resolve",
    ),

    path(
        "groups/<int:group_pk>/employees/<int:employee_pk>/archive/",
        views.archive_duplicate_employee,
        name="archive_employee",
    ),
]
