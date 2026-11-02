
from django.db import models


class Employee(models.Model):
    employee_number = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True
    )

    serial_number = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    full_name = models.CharField(max_length=200)
    gender = models.CharField(max_length=30, blank=True)

    designation = models.CharField(max_length=200, blank=True)
    job_group = models.CharField(max_length=30, blank=True)

    appointment_type = models.CharField(max_length=100, blank=True)

    date_of_arrival = models.DateField(null=True, blank=True)
    contract_period = models.CharField(max_length=100, blank=True)

    station = models.CharField(max_length=150, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)

    ethnicity = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=100, blank=True)
    remark = models.TextField(blank=True)

    # Stores additional employee information that does not
    # have a dedicated database field.
    custom_data = models.JSONField(
        default=dict,
        blank=True
    )

    is_archived = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]
        indexes = [
            models.Index(fields=["employee_number"]),
            models.Index(fields=["date_of_arrival"]),
            models.Index(fields=["station"]),
            models.Index(fields=["job_group"]),
            models.Index(fields=["status"]),
            models.Index(fields=["is_archived"]),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.employee_number or 'No ID'})"

    @property
    def joining_year(self):
        return (
            self.date_of_arrival.year
            if self.date_of_arrival
            else None
        )
