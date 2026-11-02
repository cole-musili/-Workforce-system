
from django.contrib import admin

from .models import EmployeeCustomField, ImportBatch, ImportRow


class EmployeeCustomFieldInline(admin.TabularInline):
    model = EmployeeCustomField
    extra = 0
    fields = (
        "label",
        "field_key",
        "field_type",
        "scope",
        "is_required",
        "choices",
    )


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "filename",
        "status",
        "import_mode",
        "total_rows",
        "created_count",
        "updated_count",
        "skipped_count",
        "rejected_count",
        "uploaded_at",
    )
    list_filter = ("status", "import_mode", "uploaded_at")
    search_fields = ("filename",)
    readonly_fields = (
        "uploaded_at",
        "total_rows",
        "created_count",
        "updated_count",
        "skipped_count",
        "rejected_count",
    )
    inlines = [EmployeeCustomFieldInline]


@admin.register(ImportRow)
class ImportRowAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "batch",
        "source_sheet",
        "source_period",
        "source_row_number",
        "result",
        "action",
        "employee",
        "is_selected",
    )
    list_filter = (
        "result",
        "action",
        "is_selected",
        "source_sheet",
    )
    search_fields = (
        "source_sheet",
        "source_period",
        "employee__full_name",
        "employee__employee_number",
    )
    readonly_fields = ("raw_data", "error_message")
    list_select_related = ("batch", "employee")


@admin.register(EmployeeCustomField)
class EmployeeCustomFieldAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "field_key",
        "field_type",
        "scope",
        "batch",
        "is_required",
        "created_at",
    )
    list_filter = ("field_type", "scope", "is_required")
    search_fields = ("label", "field_key")
    list_select_related = ("batch",)
