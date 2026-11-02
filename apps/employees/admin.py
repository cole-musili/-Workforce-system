
from django.contrib import admin
from .models import Employee


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "employee_number",
        "full_name",
        "gender",
        "designation",
        "job_group",
        "appointment_type",
        "station",
        "status",
        "is_archived",
        "updated_at",
    )

    search_fields = (
        "employee_number",
        "full_name",
        "designation",
        "station",
        "phone_number",
    )

    list_filter = (
        "gender",
        "job_group",
        "appointment_type",
        "station",
        "status",
        "is_archived",
    )

    ordering = ("full_name",)

    list_per_page = 25

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fieldsets = (
        ("Employee Identification", {
            "fields": (
                "employee_number",
                "serial_number",
                "full_name",
            )
        }),
        ("Employment Details", {
            "fields": (
                "gender",
                "designation",
                "job_group",
                "appointment_type",
                "date_of_arrival",
                "contract_period",
                "station",
                "status",
            )
        }),
        ("Contact & Additional Information", {
            "fields": (
                "phone_number",
                "ethnicity",
                "remark",
            )
        }),
        ("Additional Data", {
            "fields": ("custom_data",),
            "classes": ("collapse",),
        }),
        ("Record Management", {
            "fields": (
                "is_archived",
                "created_at",
                "updated_at",
            )
        }),
    )
