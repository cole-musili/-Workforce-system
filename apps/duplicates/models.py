
from django.conf import settings
from django.db import models
from django.db.models import Q


class DuplicateGroup(models.Model):
    """
    A collection of employee records identified as possible duplicates.
    """

    STATUS_CHOICES = [
        ("open", "Awaiting review"),
        ("resolved", "Resolved"),
        ("dismissed", "Not duplicates"),
    ]

    MATCH_TYPE_CHOICES = [
        ("employee_number", "Matching employee number"),
        ("national_id", "Matching national ID"),
        ("name_details", "Matching name, designation and station"),
        ("similar_name", "Similar employee names"),
        ("manual", "Manually identified"),
    ]

    fingerprint = models.CharField(
        max_length=64,
        unique=True,
        help_text="Stable identifier for this duplicate group.",
    )

    match_type = models.CharField(
        max_length=30,
        choices=MATCH_TYPE_CHOICES,
    )

    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Match confidence percentage from 0 to 100.",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="open",
        db_index=True,
    )

    description = models.TextField(blank=True)

    detection_evidence = models.JSONField(
        default=dict,
        blank=True,
        help_text="Information explaining why these records were matched.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["match_type"]),
        ]

    def __str__(self):
        return f"Duplicate group #{self.pk} ({self.get_status_display()})"


class DuplicateCandidate(models.Model):
    """
    An employee record participating in a duplicate group.
    """

    group = models.ForeignKey(
        DuplicateGroup,
        on_delete=models.CASCADE,
        related_name="candidates",
    )

    employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        related_name="duplicate_candidates",
    )

    match_basis = models.CharField(
        max_length=100,
        blank=True,
        help_text="Specific reason this employee was included.",
    )

    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
    )

    evidence = models.JSONField(
        default=dict,
        blank=True,
    )

    is_retained = models.BooleanField(default=False)

    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-confidence", "employee__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "employee"],
                name="unique_employee_per_duplicate_group",
            ),
        ]
        indexes = [
            models.Index(fields=["employee"]),
            models.Index(fields=["is_retained"]),
        ]

    def __str__(self):
        return f"{self.employee.full_name} - Group #{self.group_id}"


class DuplicateResolution(models.Model):
    """
    Records every decision made when reviewing a duplicate group.
    """

    ACTION_CHOICES = [
        ("archive_others", "Retain one and archive others"),
        ("keep_both", "Keep all records"),
        ("not_duplicate", "Mark as not duplicates"),
    ]

    group = models.ForeignKey(
        DuplicateGroup,
        on_delete=models.PROTECT,
        related_name="resolutions",
    )

    action = models.CharField(
        max_length=30,
        choices=ACTION_CHOICES,
    )

    retained_employee = models.ForeignKey(
        "employees.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="duplicate_retention_decisions",
    )

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duplicate_resolutions",
    )

    notes = models.TextField(blank=True)

    decision_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Snapshot of the records and decision at resolution time.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["group", "created_at"]),
            models.Index(fields=["action"]),
        ]

    def __str__(self):
        return f"{self.get_action_display()} - Group #{self.group_id}"
