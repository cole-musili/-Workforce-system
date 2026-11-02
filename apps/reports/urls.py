from django.urls import path
from apps.reports import views

app_name = "reports"

urlpatterns = [
    path("", views.reports_dashboard, name="dashboard"),

    path(
        "export/excel/",
        views.export_excel,
        name="export_excel",
    ),

    path(
        "export/pdf/",
        views.export_pdf,
        name="export_pdf",
    ),
]