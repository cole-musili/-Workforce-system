
from collections import defaultdict
from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify

from apps.employees.models import Employee

from .forms import (
    BulkCorrectionForm,
    ImportRowEditForm,
    ImportUploadForm,
)
from .models import EmployeeCustomField, ImportBatch, ImportRow
from .services.spreadsheet_reader import (
    get_worksheets,
    read_workbook,
)


# Standard Employee model fields that can be edited or mapped.
EDITABLE_FIELDS = [
    "serial_number",
    "employee_number",
    "full_name",
    "gender",
    "designation",
    "job_group",
    "appointment_type",
    "date_of_arrival",
    "contract_period",
    "station",
    "phone_number",
    "ethnicity",
    "status",
    "remark",
]


# Fields that must never be exposed as ordinary custom-field targets.
PROTECTED_FIELDS = {
    "id",
    "pk",
    "custom_data",
    "is_archived",
    "created_at",
    "updated_at",
}


def normalize_employee_number(value):
    """Normalize identifiers for duplicate comparisons."""

    return str(value or "").strip().casefold()


def parse_date(value):
    """Convert supported spreadsheet date formats into date objects."""

    if not value:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    value = str(value).strip()

    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%m/%d/%Y",
        "%d %b %Y",
        "%d %B %Y",
    ]

    for date_format in formats:
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue

    raise ValueError(f"Invalid date: {value}")


def get_custom_fields_for_batch(batch):
    """Return permanent custom fields and fields belonging to this batch."""

    return EmployeeCustomField.objects.filter(
        Q(scope="permanent") | Q(scope="import", batch=batch)
    ).order_by("label")


def get_row_warnings(row, batch_rows=None):
    """Return validation and review warnings for a staged row."""

    data = row.raw_data or {}
    warnings = []

    employee_number = str(
        data.get("employee_number", "")
    ).strip()

    full_name = str(
        data.get("full_name", "")
    ).strip()

    if not full_name:
        warnings.append({
            "code": "missing_name",
            "label": "Missing name",
            "severity": "danger",
        })

    if not employee_number:
        warnings.append({
            "code": "missing_number",
            "label": "Missing employee number",
            "severity": "warning",
        })

    # Detect duplicate identifiers within the selected workbook rows.
    if employee_number and batch_rows is not None:
        normalized = normalize_employee_number(employee_number)

        matching_rows = [
            other
            for other in batch_rows
            if other.pk != row.pk
            and normalize_employee_number(
                (other.raw_data or {}).get("employee_number", "")
            ) == normalized
        ]

        if matching_rows:
            sources = ", ".join(
                f"{other.source_sheet}, row {other.source_row_number}"
                for other in matching_rows[:3]
            )

            warnings.append({
                "code": "duplicate_in_batch",
                "label": "Duplicate in workbook",
                "severity": "danger",
                "detail": sources,
            })

        existing_employee = Employee.objects.filter(
            employee_number__iexact=employee_number,
            is_archived=False,
        ).first()

        if existing_employee:
            warnings.append({
                "code": "existing_employee",
                "label": "Employee already exists",
                "severity": "info",
                "detail": existing_employee.full_name,
            })

    # Detect invalid dates without rejecting the staged row.
    arrival_date = data.get("date_of_arrival", "")

    if arrival_date:
        try:
            parse_date(arrival_date)
        except (ValueError, TypeError):
            warnings.append({
                "code": "invalid_date",
                "label": "Invalid date of arrival",
                "severity": "warning",
                "detail": str(arrival_date),
            })

    # Invalid serial numbers are warnings; the employee can still be imported.
    serial_number = str(data.get("serial_number", "") or "").strip()
    if serial_number:
        try:
            if int(serial_number) < 0:
                raise ValueError
        except (ValueError, TypeError):
            warnings.append({
                "code": "invalid_serial_number",
                "label": "Invalid serial number",
                "severity": "warning",
                "detail": serial_number,
            })

    # Identify additional columns that have not been mapped.
    additional_fields = data.get("_additional_fields", {})

    if additional_fields:
        non_empty_fields = [
            name
            for name, value in additional_fields.items()
            if str(value or "").strip()
        ]

        if non_empty_fields:
            warnings.append({
                "code": "unmapped_fields",
                "label": "Unmapped spreadsheet columns",
                "severity": "warning",
                "detail": ", ".join(non_empty_fields[:5]),
            })

    # Custom-field problems are warnings, never import blockers.
    custom_values = data.get("_custom_fields", {})
    custom_fields = get_custom_fields_for_batch(row.batch)

    for custom_field in custom_fields:
        value = custom_values.get(custom_field.field_key, "")
        text_value = str(value or "").strip()

        if custom_field.is_required and not text_value:
            warnings.append({
                "code": "missing_custom_field",
                "label": f"Missing {custom_field.label}",
                "severity": "warning",
            })
            continue

        if not text_value:
            continue

        if custom_field.field_type == "number":
            try:
                float(text_value)
            except (ValueError, TypeError):
                warnings.append({
                    "code": "invalid_custom_number",
                    "label": f"Invalid number: {custom_field.label}",
                    "severity": "warning",
                    "detail": text_value,
                })

        elif custom_field.field_type == "date":
            try:
                parse_date(text_value)
            except (ValueError, TypeError):
                warnings.append({
                    "code": "invalid_custom_date",
                    "label": f"Invalid date: {custom_field.label}",
                    "severity": "warning",
                    "detail": text_value,
                })

        elif custom_field.field_type == "boolean":
            if text_value.lower() not in ["yes", "no", "true", "false", "1", "0"]:
                warnings.append({
                    "code": "invalid_custom_boolean",
                    "label": f"Invalid yes/no value: {custom_field.label}",
                    "severity": "warning",
                    "detail": text_value,
                })

        elif custom_field.field_type == "choice":
            if text_value not in (custom_field.choices or []):
                warnings.append({
                    "code": "invalid_custom_choice",
                    "label": f"Unrecognized choice: {custom_field.label}",
                    "severity": "warning",
                    "detail": text_value,
                })

    return warnings


def build_review_rows(batch):
    """Build review information for every staged row."""

    rows = list(batch.rows.all())
    review_rows = []

    for row in rows:
        warnings = get_row_warnings(row, rows)
        data = row.raw_data or {}

        has_errors = any(
            warning["severity"] == "danger"
            for warning in warnings
        )

        review_rows.append({
            "row": row,
            "data": data,
            "warnings": warnings,
            "has_errors": has_errors,
            "has_warnings": bool(warnings),
            "ready": (
                bool(str(data.get("full_name", "")).strip())
                and not has_errors
            ),
        })

    return review_rows


def stage_selected_sheets(batch, selected_sheets):
    """Read selected worksheets and save their records for review."""

    batch.uploaded_file.open("rb")

    try:
        result = read_workbook(
            batch.uploaded_file,
            selected_sheets,
        )
    finally:
        batch.uploaded_file.close()

    staged_rows = []

    for record in result["records"]:
        staged_rows.append(
            ImportRow(
                batch=batch,
                source_sheet=record["source_sheet"],
                source_period=record.get("source_period", ""),
                source_row_number=record["source_row_number"],
                raw_data=record["raw_data"],
            )
        )

    with transaction.atomic():
        batch.rows.all().delete()

        ImportRow.objects.bulk_create(
            staged_rows,
            batch_size=500,
        )

        batch.selected_sheets = selected_sheets
        batch.detected_headers = result["detected_headers"]
        batch.total_rows = result["total_rows"]
        batch.status = "previewed"

        batch.save(update_fields=[
            "selected_sheets",
            "detected_headers",
            "total_rows",
            "status",
        ])

    return result


@login_required
def import_upload(request):
    """Upload a CSV or Excel workbook."""

    if request.method == "POST":
        form = ImportUploadForm(
            request.POST,
            request.FILES,
        )

        if form.is_valid():
            uploaded_file = form.cleaned_data["uploaded_file"]
            batch = None

            try:
                batch = form.save(commit=False)
                batch.filename = uploaded_file.name
                batch.status = "pending"
                batch.save()

                batch.uploaded_file.open("rb")

                try:
                    worksheets = get_worksheets(batch.uploaded_file)
                finally:
                    batch.uploaded_file.close()

                # Single-sheet files proceed directly to review.
                if len(worksheets) == 1:
                    result = stage_selected_sheets(
                        batch,
                        worksheets,
                    )

                    messages.success(
                        request,
                        f"Successfully staged {result['total_rows']} records.",
                    )

                    return redirect(
                        "imports:review",
                        batch_id=batch.pk,
                    )

                return redirect(
                    "imports:select_worksheets",
                    batch_id=batch.pk,
                )

            except Exception as error:
                if batch is not None:
                    batch.status = "failed"
                    batch.save(update_fields=["status"])

                messages.error(
                    request,
                    f"Unable to process uploaded file: {error}",
                )

                form.add_error(
                    "uploaded_file",
                    str(error),
                )

    else:
        form = ImportUploadForm()

    return render(
        request,
        "imports/upload.html",
        {"form": form},
    )


@login_required
def select_worksheets(request, batch_id):
    """Allow the user to choose which worksheets to import."""

    batch = get_object_or_404(
        ImportBatch,
        pk=batch_id,
        status="pending",
    )

    batch.uploaded_file.open("rb")

    try:
        available_sheets = get_worksheets(batch.uploaded_file)
    finally:
        batch.uploaded_file.close()

    if request.method == "POST":
        selected_sheets = request.POST.getlist("worksheets")

        if not selected_sheets:
            messages.error(
                request,
                "Select at least one worksheet.",
            )

            return redirect(
                "imports:select_worksheets",
                batch_id=batch.pk,
            )

        if not set(selected_sheets).issubset(set(available_sheets)):
            messages.error(request, "Invalid worksheet selection.")

            return redirect("imports:upload")

        try:
            stage_selected_sheets(batch, selected_sheets)

            messages.success(
                request,
                "Selected worksheets processed successfully.",
            )

            return redirect(
                "imports:review",
                batch_id=batch.pk,
            )

        except Exception as error:
            messages.error(request, str(error))

            return render(
                request,
                "imports/select_worksheets.html",
                {
                    "batch": batch,
                    "worksheets": available_sheets,
                },
            )

    return render(
        request,
        "imports/select_worksheets.html",
        {
            "batch": batch,
            "worksheets": available_sheets,
        },
    )


@login_required
def review_batch(request, batch_id):
    """Display the staged rows and their validation status."""

    batch = get_object_or_404(ImportBatch, pk=batch_id)

    if batch.status == "processing":
        messages.info(request, "This import batch is currently processing.")
        return redirect("imports:history")

    if batch.status == "previewed":
        batch.status = "reviewing"
        batch.save(update_fields=["status"])

    review_rows = build_review_rows(batch)

    missing_names = sum(
        1 for item in review_rows
        if not str(item["data"].get("full_name", "")).strip()
    )

    missing_numbers = sum(
        1 for item in review_rows
        if not str(item["data"].get("employee_number", "")).strip()
    )

    duplicate_rows = sum(
        1 for item in review_rows
        if any(
            warning["code"] == "duplicate_in_batch"
            for warning in item["warnings"]
        )
    )

    ready_count = sum(
        1 for item in review_rows
        if item["ready"]
    )

    filter_value = request.GET.get("filter", "all")

    if filter_value == "missing_name":
        review_rows = [
            item for item in review_rows
            if not str(item["data"].get("full_name", "")).strip()
        ]

    elif filter_value == "missing_number":
        review_rows = [
            item for item in review_rows
            if not str(item["data"].get("employee_number", "")).strip()
        ]

    elif filter_value == "duplicates":
        review_rows = [
            item for item in review_rows
            if any(
                warning["code"] == "duplicate_in_batch"
                for warning in item["warnings"]
            )
        ]

    elif filter_value == "ready":
        review_rows = [
            item for item in review_rows
            if item["ready"]
        ]

    elif filter_value == "errors":
        review_rows = [
            item for item in review_rows
            if item["has_errors"]
        ]

    return render(
        request,
        "imports/review.html",
        {
            "batch": batch,
            "review_rows": review_rows,
            "missing_names": missing_names,
            "missing_numbers": missing_numbers,
            "duplicate_rows": duplicate_rows,
            "ready_count": ready_count,
            "filter_value": filter_value,
            "custom_fields": get_custom_fields_for_batch(batch),
        },
    )


@login_required
def edit_import_row(request, batch_id, row_id):
    """Edit one staged row, including its custom field values."""

    batch = get_object_or_404(
        ImportBatch,
        pk=batch_id,
    )

    if batch.status not in ["previewed", "reviewing", "completed"]:
        messages.error(request, "This batch is no longer editable.")
        return redirect("imports:history")

    row = get_object_or_404(
        ImportRow,
        pk=row_id,
        batch=batch,
    )

    if batch.status == "completed" and row.result not in ["rejected", "skipped"]:
        messages.error(request, "Only rejected or skipped rows can be corrected after completion.")
        return redirect("imports:history")

    custom_fields = list(get_custom_fields_for_batch(batch))

    if request.method == "POST":
        form = ImportRowEditForm(request.POST)

        if form.is_valid():
            data = row.raw_data or {}

            for field in EDITABLE_FIELDS:
                data[field] = form.cleaned_data.get(field, "")

            custom_values = data.get("_custom_fields", {})

            for custom_field in custom_fields:
                input_name = f"custom_{custom_field.pk}"

                if input_name in request.POST:
                    custom_values[custom_field.field_key] = (
                        request.POST.get(input_name, "").strip()
                    )

            data["_custom_fields"] = custom_values

            row.raw_data = data

            # A corrected rejected/skipped row becomes eligible for a retry.
            if row.result in ["rejected", "skipped"]:
                row.result = "pending"
                row.error_message = ""
                row.is_selected = True

            row.save(update_fields=["raw_data", "result", "error_message", "is_selected"])

            if batch.status == "completed":
                batch.status = "reviewing"
                batch.save(update_fields=["status"])

            messages.success(
                request,
                "Staged employee record updated. It is ready for review/import.",
            )

            return redirect(
                "imports:review",
                batch_id=batch.pk,
            )

    else:
        initial = row.raw_data or {}

        form = ImportRowEditForm(initial=initial)

    custom_values = (row.raw_data or {}).get("_custom_fields", {})

    custom_field_inputs = []

    for custom_field in custom_fields:
        custom_field_inputs.append({
            "field": custom_field,
            "current_value": custom_values.get(
                custom_field.field_key,
                "",
            ),
        })

    return render(
        request,
        "imports/edit_row.html",
        {
            "batch": batch,
            "row": row,
            "form": form,
            "custom_fields": custom_field_inputs,
        },
    )


@login_required
def update_row_action(request, batch_id, row_id):
    """Change the action selected for an individual row."""

    batch = get_object_or_404(
        ImportBatch,
        pk=batch_id,
    )

    row = get_object_or_404(
        ImportRow,
        pk=row_id,
        batch=batch,
    )

    if request.method == "POST":
        action = request.POST.get("action", "auto")

        valid_actions = [
            choice[0]
            for choice in ImportRow.ACTION_CHOICES
        ]

        if (
            action in valid_actions
            and batch.status in ["previewed", "reviewing"]
        ):
            row.action = action
            row.save(update_fields=["action"])

            messages.success(request, "Row action updated.")

    return redirect(
        "imports:review",
        batch_id=batch.pk,
    )


@login_required
def update_selection(request, batch_id):
    """Select or deselect staged rows for importing."""

    batch = get_object_or_404(
        ImportBatch,
        pk=batch_id,
    )

    if request.method == "POST" and batch.status in [
        "previewed",
        "reviewing",
    ]:
        selected_ids = request.POST.getlist("selected_rows")

        rows = batch.rows.all()

        rows.update(is_selected=False)

        if selected_ids:
            rows.filter(pk__in=selected_ids).update(
                is_selected=True,
            )

        messages.success(
            request,
            "Import row selection updated.",
        )

    return redirect(
        "imports:review",
        batch_id=batch.pk,
    )


@login_required
def bulk_correct(request, batch_id):
    """Apply one correction to multiple staged rows."""

    batch = get_object_or_404(
        ImportBatch,
        pk=batch_id,
    )

    if batch.status not in ["previewed", "reviewing"]:
        messages.error(request, "This batch is no longer editable.")
        return redirect("imports:history")

    selected_ids = request.POST.getlist("selected_rows")

    if request.method == "POST":
        form = BulkCorrectionForm(request.POST)

        if form.is_valid():
            field_name = form.cleaned_data["field_name"]
            value = form.cleaned_data["value"]
            overwrite = form.cleaned_data["overwrite_existing"]

            rows = batch.rows.filter(pk__in=selected_ids)

            updated_count = 0

            with transaction.atomic():
                for row in rows:
                    data = row.raw_data or {}

                    current_value = str(
                        data.get(field_name, "")
                    ).strip()

                    if current_value and not overwrite:
                        continue

                    data[field_name] = value
                    row.raw_data = data

                    row.save(update_fields=["raw_data"])
                    updated_count += 1

            messages.success(
                request,
                f"Bulk correction applied to {updated_count} rows.",
            )

            return redirect(
                "imports:review",
                batch_id=batch.pk,
            )

    else:
        form = BulkCorrectionForm()

    return render(
        request,
        "imports/bulk_correct.html",
        {
            "batch": batch,
            "form": form,
            "selected_count": len(selected_ids),
            "selected_ids": selected_ids,
        },
    )


@login_required
def manage_custom_fields(request, batch_id):
    """
    Manage spreadsheet column mappings and custom fields.

    POST actions:
      map_standard: map a source column to a standard Employee field.
      create_custom: create a permanent or batch-specific custom field.
      map_custom: map a source column to an existing custom field.
    """

    batch = get_object_or_404(
        ImportBatch,
        pk=batch_id,
    )

    if batch.status not in ["previewed", "reviewing"]:
        messages.error(request, "This batch can no longer be edited.")
        return redirect("imports:history")

    rows = list(batch.rows.all())

    available_columns = []

    for row in rows:
        data = row.raw_data or {}

        source_columns = data.get("_source_columns", {})
        additional_fields = data.get("_additional_fields", {})

        for column in list(source_columns) + list(additional_fields):
            if column not in available_columns:
                available_columns.append(column)

    existing_custom_fields = list(
        get_custom_fields_for_batch(batch)
    )

    if request.method == "POST":
        action = request.POST.get("action", "")

        source_column = request.POST.get(
            "source_column",
            "",
        ).strip()

        if action in ["map_standard", "map_custom"]:
            if source_column not in available_columns:
                messages.error(request, "Invalid source column.")

                return redirect(
                    "imports:custom_fields",
                    batch_id=batch.pk,
                )

            target_field = request.POST.get(
                "target_field",
                "",
            ).strip()

            if action == "map_standard":
                if target_field not in EDITABLE_FIELDS:
                    messages.error(
                        request,
                        "Invalid standard employee field.",
                    )

                    return redirect(
                        "imports:custom_fields",
                        batch_id=batch.pk,
                    )

                for row in rows:
                    data = row.raw_data or {}
                    source_values = data.get("_source_columns", {})

                    if source_column not in source_values:
                        continue

                    value = source_values[source_column]

                    if target_field == "date_of_arrival" and value:
                        try:
                            value = parse_date(value).isoformat()
                        except (ValueError, TypeError):
                            pass

                    data[target_field] = value
                    row.raw_data = data

                    row.save(update_fields=["raw_data"])

                messages.success(
                    request,
                    f"Mapped '{source_column}' to {target_field}.",
                )

            else:
                custom_field = get_object_or_404(
                    EmployeeCustomField,
                    pk=target_field,
                )

                if (
                    custom_field.scope == "import"
                    and custom_field.batch_id != batch.pk
                ):
                    messages.error(
                        request,
                        "That custom field belongs to another import.",
                    )

                    return redirect(
                        "imports:custom_fields",
                        batch_id=batch.pk,
                    )

                for row in rows:
                    data = row.raw_data or {}
                    source_values = data.get("_source_columns", {})

                    if source_column not in source_values:
                        continue

                    custom_values = data.get("_custom_fields", {})

                    custom_values[custom_field.field_key] = (
                        source_values[source_column]
                    )

                    data["_custom_fields"] = custom_values
                    row.raw_data = data

                    row.save(update_fields=["raw_data"])

                messages.success(
                    request,
                    f"Mapped '{source_column}' to "
                    f"{custom_field.label}.",
                )

            return redirect(
                "imports:custom_fields",
                batch_id=batch.pk,
            )

        elif action == "create_custom":
            label = request.POST.get("label", "").strip()
            field_type = request.POST.get("field_type", "text")
            scope = request.POST.get("scope", "import")
            is_required = request.POST.get("is_required") == "on"

            allowed_types = {
                choice[0]
                for choice in EmployeeCustomField.FIELD_TYPE_CHOICES
            }

            if not label:
                messages.error(request, "Enter a custom field name.")

            elif field_type not in allowed_types:
                messages.error(request, "Invalid custom field type.")

            elif scope not in ["permanent", "import"]:
                messages.error(request, "Invalid custom field scope.")

            else:
                field_key = slugify(label)

                if not field_key:
                    messages.error(
                        request,
                        "The field name must contain letters or numbers.",
                    )

                else:
                    if scope == "permanent":
                        duplicate = EmployeeCustomField.objects.filter(
                            scope="permanent",
                            field_key=field_key,
                        ).exists()
                    else:
                        duplicate = EmployeeCustomField.objects.filter(
                            scope="import",
                            batch=batch,
                            field_key=field_key,
                        ).exists()

                    if duplicate:
                        messages.error(
                            request,
                            "A custom field with that name already exists.",
                        )

                    else:
                        choices = []

                        if field_type == "choice":
                            choices = [
                                item.strip()
                                for item in request.POST.get(
                                    "choices",
                                    "",
                                ).splitlines()
                                if item.strip()
                            ]

                            if not choices:
                                messages.error(
                                    request,
                                    "Enter at least one choice.",
                                )

                                return redirect(
                                    "imports:custom_fields",
                                    batch_id=batch.pk,
                                )

                        custom_field = EmployeeCustomField.objects.create(
                            label=label,
                            field_key=field_key,
                            field_type=field_type,
                            scope=scope,
                            batch=batch if scope == "import" else None,
                            is_required=is_required,
                            choices=choices,
                        )

                        if source_column in available_columns:
                            for row in rows:
                                data = row.raw_data or {}
                                source_values = data.get(
                                    "_source_columns",
                                    {},
                                )

                                if source_column not in source_values:
                                    continue

                                custom_values = data.get(
                                    "_custom_fields",
                                    {},
                                )

                                custom_values[custom_field.field_key] = (
                                    source_values[source_column]
                                )

                                data["_custom_fields"] = custom_values
                                row.raw_data = data

                                row.save(update_fields=["raw_data"])

                        messages.success(
                            request,
                            f"Custom field '{label}' created successfully.",
                        )

            return redirect(
                "imports:custom_fields",
                batch_id=batch.pk,
            )

        else:
            messages.error(request, "Unknown custom-field action.")

            return redirect(
                "imports:custom_fields",
                batch_id=batch.pk,
            )

    return render(
        request,
        "imports/custom_fields.html",
        {
            "batch": batch,
            "available_columns": available_columns,
            "standard_fields": [
                {
                    "name": field,
                    "label": field.replace("_", " ").title(),
                }
                for field in EDITABLE_FIELDS
            ],
            "custom_fields": existing_custom_fields,
        },
    )


def get_import_decision(batch, row, existing_employee):
    """Resolve the automatic or manually selected import action."""

    if row.action == "skip":
        return "skip"

    if row.action == "add":
        return "add"

    if row.action == "update":
        return "update"

    if batch.import_mode == "add_only":
        return "skip" if existing_employee else "add"

    if batch.import_mode == "update_existing":
        return "update" if existing_employee else "skip"

    return "update" if existing_employee else "add"


def _safe_parse_date(value):
    """Return a parsed date, or None for invalid/blank input.

    Invalid dates remain visible in the staged source data and are reported
    as warnings; they must not block an otherwise valid employee import.
    """
    if not value:
        return None
    try:
        return parse_date(value)
    except (ValueError, TypeError):
        return None


def employee_values_from_row(data):
    """Convert staged standard fields into Employee model values."""

    full_name = str(data.get("full_name", "")).strip()

    if not full_name:
        raise ValueError("Employee name is missing.")

    employee_number = str(
        data.get("employee_number", "")
    ).strip() or None

    serial_number = str(
        data.get("serial_number", "")
    ).strip()

    if serial_number:
        try:
            serial_number = int(serial_number)
        except (ValueError, TypeError):
            serial_number = None

        if serial_number is not None and serial_number < 0:
            serial_number = None

    else:
        serial_number = None

    return {
        "employee_number": employee_number,
        "serial_number": serial_number,
        "full_name": full_name,
        "gender": str(data.get("gender", "")).strip(),
        "designation": str(data.get("designation", "")).strip(),
        "job_group": str(data.get("job_group", "")).strip(),
        "appointment_type": str(
            data.get("appointment_type", "")
        ).strip(),
        "date_of_arrival": _safe_parse_date(
            data.get("date_of_arrival", "")
        ),
        "contract_period": str(
            data.get("contract_period", "")
        ).strip(),
        "station": str(data.get("station", "")).strip(),
        "phone_number": str(data.get("phone_number", "")).strip(),
        "ethnicity": str(data.get("ethnicity", "")).strip(),
        "status": str(data.get("status", "")).strip(),
        "remark": str(data.get("remark", "")).strip(),
    }


def validate_custom_values(batch, data):
    """Return staged custom values without blocking imports.

    Custom-field issues are surfaced by get_row_warnings(). They are not
    reasons to reject an employee record.
    """
    return data.get("_custom_fields", {}) or {}


@login_required
def confirm_import(request, batch_id):
    """Validate and commit the selected staged rows."""

    batch = get_object_or_404(
        ImportBatch,
        pk=batch_id,
    )

    if batch.status not in ["previewed", "reviewing"]:
        messages.error(request, "This batch cannot be imported.")
        return redirect("imports:history")

    selected_rows = batch.rows.filter(
        is_selected=True,
        result="pending",
    ).order_by("source_sheet", "source_row_number")

    if request.method == "GET":
        return render(
            request,
            "imports/confirm.html",
            {
                "batch": batch,
                "selected_rows": selected_rows,
                "selected_count": selected_rows.count(),
            },
        )

    if request.method != "POST":
        return redirect(
            "imports:confirm",
            batch_id=batch.pk,
        )

    if request.POST.get("confirm_import") != "yes":
        messages.error(
            request,
            "Please confirm before importing.",
        )

        return redirect(
            "imports:confirm",
            batch_id=batch.pk,
        )

    rows = list(selected_rows)

    if not rows:
        messages.error(
            request,
            "There are no selected pending rows to import.",
        )

        return redirect(
            "imports:review",
            batch_id=batch.pk,
        )

    # Identify duplicate employee numbers within the selected rows.
    identifier_groups = defaultdict(list)

    for row in rows:
        identifier = normalize_employee_number(
            (row.raw_data or {}).get("employee_number", "")
        )

        if identifier:
            identifier_groups[identifier].append(row)

    conflicting_ids = {
        identifier
        for identifier, grouped_rows in identifier_groups.items()
        if len(grouped_rows) > 1
    }

    created_count = batch.rows.filter(result="created").count()
    updated_count = batch.rows.filter(result="updated").count()
    skipped_count = 0
    rejected_count = 0

    try:
        with transaction.atomic():
            batch.status = "processing"
            batch.save(update_fields=["status"])

            for row in rows:
                data = row.raw_data or {}

                employee_number = str(
                    data.get("employee_number", "")
                ).strip()

                normalized_identifier = normalize_employee_number(
                    employee_number
                )

                # Duplicate identifiers require explicit resolution.
                if (
                    normalized_identifier
                    and normalized_identifier in conflicting_ids
                ):
                    conflicting_rows = identifier_groups[normalized_identifier]
                    conflict_locations = ", ".join(
                        f"{item.source_sheet}, Excel row {item.source_row_number}"
                        for item in conflicting_rows
                    )
                    row.result = "rejected"
                    row.error_message = (
                        f"Duplicate P/No. '{employee_number}' appears in: "
                        f"{conflict_locations}. Inspect the records, correct "
                        "the identifier if necessary, or deselect the record "
                        "you do not want to import."
                    )

                    row.save(update_fields=[
                        "result",
                        "error_message",
                    ])

                    rejected_count += 1
                    continue

                if not str(data.get("full_name", "")).strip():
                    row.result = "rejected"
                    row.error_message = "Employee name is missing. Add the employee name before retrying this record."
                    row.save(update_fields=["result", "error_message"])
                    rejected_count += 1
                    continue

                existing_employee = None

                if employee_number:
                    existing_employee = Employee.objects.filter(
                        employee_number__iexact=employee_number,
                        is_archived=False,
                    ).first()

                decision = get_import_decision(
                    batch,
                    row,
                    existing_employee,
                )

                if decision == "skip":
                    row.result = "skipped"
                    row.error_message = (
                        "Skipped according to the selected import action "
                        "or import mode."
                    )

                    row.save(update_fields=[
                        "result",
                        "error_message",
                    ])

                    skipped_count += 1
                    continue

                if decision == "update" and not existing_employee:
                    row.result = "skipped"
                    row.error_message = (
                        "No existing employee was found to update."
                    )

                    row.save(update_fields=[
                        "result",
                        "error_message",
                    ])

                    skipped_count += 1
                    continue

                # A nested atomic block creates a savepoint for each row.
                # A database error in one row will not poison the batch.
                try:
                    with transaction.atomic():
                        values = employee_values_from_row(data)

                        custom_values = validate_custom_values(
                            batch,
                            data,
                        )

                        if decision == "add":
                            if values["employee_number"]:
                                collision = Employee.objects.filter(
                                    employee_number__iexact=(
                                        values["employee_number"]
                                    )
                                ).exists()

                                if collision:
                                    raise ValueError(
                                        "Employee number already exists. "
                                        "Choose Update or Skip instead."
                                    )

                            employee = Employee.objects.create(
                                **values,
                                custom_data=custom_values,
                            )

                            row.employee = employee
                            row.result = "created"
                            row.error_message = ""

                            row.save(update_fields=[
                                "employee",
                                "result",
                                "error_message",
                            ])

                            created_count += 1

                        elif decision == "update":
                            # Blank incoming standard fields must not erase
                            # existing employee information.
                            for field, value in values.items():
                                if value not in ("", None):
                                    setattr(
                                        existing_employee,
                                        field,
                                        value,
                                    )

                            # Merge custom data instead of replacing it.
                            existing_custom_data = (
                                existing_employee.custom_data or {}
                            )

                            for key, value in custom_values.items():
                                if value not in ("", None):
                                    existing_custom_data[key] = value

                            existing_employee.custom_data = (
                                existing_custom_data
                            )

                            existing_employee.save()

                            row.employee = existing_employee
                            row.result = "updated"
                            row.error_message = ""

                            row.save(update_fields=[
                                "employee",
                                "result",
                                "error_message",
                            ])

                            updated_count += 1

                except (ValueError, IntegrityError) as error:
                    row.result = "rejected"
                    row.error_message = str(error)

                    row.save(update_fields=[
                        "result",
                        "error_message",
                    ])

                    rejected_count += 1

            skipped_count = batch.rows.filter(result="skipped").count()
            rejected_count = batch.rows.filter(result="rejected").count()

            batch.created_count = created_count
            batch.updated_count = updated_count
            batch.skipped_count = skipped_count
            batch.rejected_count = rejected_count
            batch.status = "completed"

            batch.save(update_fields=[
                "created_count",
                "updated_count",
                "skipped_count",
                "rejected_count",
                "status",
            ])

    except Exception as error:
        batch.refresh_from_db()
        batch.status = "reviewing"
        batch.save(update_fields=["status"])

        messages.error(
            request,
            f"Import could not be completed: {error}",
        )

        return redirect(
            "imports:review",
            batch_id=batch.pk,
        )

    messages.success(
        request,
        (
            f"Import completed. Added: {created_count}, "
            f"updated: {updated_count}, skipped: {skipped_count}, "
            f"rejected: {rejected_count}."
        ),
    )

    return redirect("imports:history")


@login_required
def import_history(request):
    """Display previous import batches."""

    batches = ImportBatch.objects.order_by("-uploaded_at")

    return render(
        request,
        "imports/history.html",
        {"batches": batches},
    )
