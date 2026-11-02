
from django import forms

from .models import Employee


class EmployeeForm(forms.ModelForm):

    class Meta:
        model = Employee

        fields = [
            "employee_number",
            "serial_number",
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

        widgets = {
            "employee_number": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter employee number",
            }),

            "serial_number": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "Enter serial number",
                "min": 1,
            }),

            "full_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter employee full name",
            }),

            "gender": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter gender",
            }),

            "designation": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter designation",
            }),

            "job_group": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter job group",
            }),

            "appointment_type": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter appointment type",
            }),

            "date_of_arrival": forms.DateInput(attrs={
                "type": "date",
                "class": "form-control",
            }),

            "contract_period": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter contract period",
            }),

            "station": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter station",
            }),

            "phone_number": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter phone number",
            }),

            "ethnicity": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter ethnicity",
            }),

            "status": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter employment status",
            }),

            "remark": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Additional remarks...",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["full_name"].required = True

        # Employee number is optional because some source records
        # may not contain an official employee number.
        self.fields["employee_number"].required = False

        # Add consistent Bootstrap styling and labels.
        for name, field in self.fields.items():
            field.widget.attrs.setdefault(
                "class",
                "form-control"
            )

            field.widget.attrs.setdefault(
                "placeholder",
                field.label
            )

    def clean_full_name(self):
        full_name = self.cleaned_data.get("full_name", "")
        full_name = " ".join(full_name.split())

        if not full_name:
            raise forms.ValidationError(
                "Employee full name is required."
            )

        return full_name

    def clean_employee_number(self):
        employee_number = self.cleaned_data.get("employee_number")

        if employee_number:
            employee_number = employee_number.strip()

        return employee_number or None
