from django import forms
from django.contrib.auth import get_user_model


User = get_user_model()


class ProfileForm(forms.ModelForm):
    """Allow a signed-in user to edit their own basic profile details."""

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")
        widgets = {
            "first_name": forms.TextInput(attrs={
                "class": "form-control",
                "autocomplete": "given-name",
                "placeholder": "First name",
            }),
            "last_name": forms.TextInput(attrs={
                "class": "form-control",
                "autocomplete": "family-name",
                "placeholder": "Last name",
            }),
            "email": forms.EmailInput(attrs={
                "class": "form-control",
                "autocomplete": "email",
                "placeholder": "name@example.com",
            }),
        }
        labels = {
            "first_name": "First name",
            "last_name": "Last name",
            "email": "Email address",
        }
