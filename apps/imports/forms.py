
from datetime import datetime

from django import forms

from .models import ImportBatch


BOOTSTRAP_INPUT = {"class": "form-control"}
BOOTSTRAP_SELECT = {"class": "form-select"}


class ImportUploadForm(forms.ModelForm):

    class Meta:
        model = ImportBatch
        fields = ["uploaded_file"]
        widgets = {
            "uploaded_file": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                    "accept": ".csv,.xlsx,.xls",
                }
            )
        }

    def clean_uploaded_file(self):
        uploaded_file = self.cleaned_data["uploaded_file"]

        allowed_extensions = (".csv", ".xlsx", ".xls")

        if not uploaded_file.name.lower().endswith(allowed_extensions):
            raise forms.ValidationError(
                "Unsupported file format. Upload CSV, XLSX or XLS."
            )

        if uploaded_file.size > 10 * 1024 * 1024:
            raise forms.ValidationError(
                "File size cannot exceed 10 MB."
            )

        return uploaded_file


class ImportRowEditForm(forms.Form):
    """
    Form for correcting standard employee fields in a staged row.

    Full name is deliberately optional here because incomplete records
    must remain editable during the review process.
    """

    serial_number = forms.CharField(
        required=False,
        label="Serial number",
        widget=forms.TextInput(attrs=BOOTSTRAP_INPUT),
    )

    employee_number = forms.CharField(
        required=False,
        label="Employee number (P/No.)",
        max_length=50,
        widget=forms.TextInput(attrs=BOOTSTRAP_INPUT),
    )

    full_name = forms.CharField(
        required=False,
        label="Full name",
        max_length=200,
        widget=forms.TextInput(attrs=BOOTSTRAP_INPUT),
    )

    gender = forms.CharField(
        required=False,
        max_length=30,
        widget=forms.TextInput(attrs=BOOTSTRAP_INPUT),
    )

    designation = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs=BOOTSTRAP_INPUT),
    )

    job_group = forms.CharField(
        required=False,
        max_length=30,
        widget=forms.TextInput(attrs=BOOTSTRAP_INPUT),
    )

    appointment_type = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs=BOOTSTRAP_INPUT),
    )

    date_of_arrival = forms.CharField(
        required=False,
        label="Date of arrival",
        widget=forms.TextInput(
            attrs={
                **BOOTSTRAP_INPUT,
                "placeholder": "YYYY-MM-DD",
            }
        ),
    )

    contract_period = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs=BOOTSTRAP_INPUT),
    )

    station = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs=BOOTSTRAP_INPUT),
    )

    phone_number = forms.CharField(
        required=False,
        max_length=30,
        widget=forms.TextInput(attrs=BOOTSTRAP_INPUT),
    )

    ethnicity = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs=BOOTSTRAP_INPUT),
    )

    status = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs=BOOTSTRAP_INPUT),
    )

    remark = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
            }
        ),
    )

    def clean_serial_number(self):
        value = self.cleaned_data.get("serial_number", "").strip()

        if not value:
            return ""

        try:
            number = int(value)
        except (ValueError, TypeError):
            raise forms.ValidationError(
                "Enter a valid whole serial number."
            )

        if number < 0:
            raise forms.ValidationError(
                "Serial number cannot be negative."
            )

        return str(number)

    def clean_date_of_arrival(self):
        value = self.cleaned_data.get(
            "date_of_arrival", ""
        ).strip()

        if not value:
            return ""

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
                parsed_date = datetime.strptime(
                    value,
                    date_format,
                )

                return parsed_date.date().isoformat()

            except ValueError:
                continue

        raise forms.ValidationError(
            "Use YYYY-MM-DD or DD/MM/YYYY."
        )


class BulkCorrectionForm(forms.Form):
    """
    Applies one standard employee-field correction to selected rows.
    """

    FIELD_CHOICES = [
        ("gender", "Gender"),
        ("designation", "Designation"),
        ("job_group", "Job group"),
        ("appointment_type", "Appointment type"),
        ("contract_period", "Contract period"),
        ("station", "Station"),
        ("status", "Status"),
    ]

    field_name = forms.ChoiceField(
        choices=FIELD_CHOICES,
        widget=forms.Select(attrs=BOOTSTRAP_SELECT),
    )

    value = forms.CharField(
        max_length=200,
        widget=forms.TextInput(
            attrs={
                **BOOTSTRAP_INPUT,
                "placeholder": "Enter the value to apply",
            }
        ),
    )

    overwrite_existing = forms.BooleanField(
        required=False,
        initial=False,
        label="Overwrite existing non-empty values",
        widget=forms.CheckboxInput(
            attrs={"class": "form-check-input"}
        ),
    )

    def clean_value(self):
        value = self.cleaned_data["value"].strip()

        if not value:
            raise forms.ValidationError(
                "Enter a value to apply."
            )

        return value
