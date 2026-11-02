
from django.db import models
from django.utils.text import slugify


class ImportBatch(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("previewed", "Previewed"),
        ("reviewing", "Reviewing"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    IMPORT_MODE_CHOICES = [
        ("add_only", "Add new employees only"),
        ("update_existing", "Update existing employees"),
        ("add_update", "Add new and update existing employees"),
    ]

    filename = models.CharField(max_length=255)

    uploaded_file = models.FileField(
        upload_to="imports/%Y/%m/"
    )

    uploaded_at = models.DateTimeField(auto_now_add=True)

    import_mode = models.CharField(
        max_length=30,
        choices=IMPORT_MODE_CHOICES,
        default="add_update",
    )

    selected_sheets = models.JSONField(default=list, blank=True)
    detected_headers = models.JSONField(default=dict, blank=True)

    total_rows = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    rejected_count = models.PositiveIntegerField(default=0)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    def __str__(self):
        return f"{self.filename} ({self.uploaded_at:%Y-%m-%d})"


class ImportRow(models.Model):

    RESULT_CHOICES = [
        ("pending", "Pending"),
        ("created", "Created"),
        ("updated", "Updated"),
        ("skipped", "Skipped"),
        ("rejected", "Rejected"),
    ]

    ACTION_CHOICES = [
        ("auto", "Automatic"),
        ("add", "Add as new employee"),
        ("update", "Update existing employee"),
        ("skip", "Skip this row"),
    ]

    batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.CASCADE,
        related_name="rows",
    )

    source_sheet = models.CharField(
        max_length=255,
        blank=True,
    )

    source_period = models.CharField(
        max_length=30,
        blank=True,
    )

    source_row_number = models.PositiveIntegerField()

    raw_data = models.JSONField(default=dict, blank=True)

    is_selected = models.BooleanField(default=True)

    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        default="auto",
    )

    employee = models.ForeignKey(
        "employees.Employee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    result = models.CharField(
        max_length=30,
        choices=RESULT_CHOICES,
        default="pending",
    )

    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["source_sheet", "source_row_number"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "batch",
                    "source_sheet",
                    "source_row_number",
                ],
                name="unique_import_sheet_source_row",
            )
        ]

    def __str__(self):
        return (
            f"{self.batch.filename} - "
            f"{self.source_sheet} - "
            f"Row {self.source_row_number}"
        )


class EmployeeCustomField(models.Model):
    """
    Defines additional employee fields.

    Permanent fields can be reused across imports.
    Import-specific fields belong to one ImportBatch.
    """

    FIELD_TYPE_CHOICES = [
        ("text", "Text"),
        ("number", "Number"),
        ("date", "Date"),
        ("boolean", "Yes / No"),
        ("choice", "Choice"),
    ]

    SCOPE_CHOICES = [
        ("permanent", "Permanent employee field"),
        ("import", "This import only"),
    ]

    label = models.CharField(max_length=150)

    field_key = models.SlugField(
        max_length=160,
        blank=True,
    )

    field_type = models.CharField(
        max_length=20,
        choices=FIELD_TYPE_CHOICES,
        default="text",
    )

    scope = models.CharField(
        max_length=20,
        choices=SCOPE_CHOICES,
        default="permanent",
    )

    choices = models.JSONField(
        default=list,
        blank=True,
        help_text="Options used when the field type is Choice.",
    )

    is_required = models.BooleanField(default=False)

    batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="custom_fields",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["label"]

        constraints = [
            models.UniqueConstraint(
                fields=["field_key"],
                condition=models.Q(scope="permanent"),
                name="unique_permanent_employee_custom_field",
            ),
            models.UniqueConstraint(
                fields=["batch", "field_key"],
                condition=models.Q(scope="import"),
                name="unique_import_custom_field_per_batch",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.field_key:
            self.field_key = slugify(self.label)

        if self.scope == "permanent":
            self.batch = None

        super().save(*args, **kwargs)

    def __str__(self):
        return self.label
