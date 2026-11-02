
from django.urls import path
from . import views

urlpatterns = [
    # Active employees
    path("", views.employee_list, name="employee_list"),
    path("add/", views.employee_create, name="employee_create"),

    # Archived employees
    path("archived/", views.archived_employee_list, name="archived_employee_list"),
    path(
        "archived/<int:pk>/restore/",
        views.employee_restore,
        name="employee_restore",
    ),

    # Individual employee records
    path("<int:pk>/", views.employee_detail, name="employee_detail"),
    path("<int:pk>/edit/", views.employee_update, name="employee_update"),
    path("<int:pk>/archive/", views.employee_archive, name="employee_archive"),
]
