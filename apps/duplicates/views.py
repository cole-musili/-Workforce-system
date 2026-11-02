
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.duplicates.models import (
    DuplicateGroup,
    DuplicateCandidate,
    DuplicateResolution,
)
from apps.employees.models import Employee


@login_required
def duplicate_dashboard(request):
    groups = DuplicateGroup.objects.all()

    context = {
        "total_groups": groups.count(),
        "open_groups": groups.filter(status="open").count(),
        "resolved_groups": groups.filter(status="resolved").count(),
        "dismissed_groups": groups.filter(status="dismissed").count(),
        "strong_groups": groups.filter(match_type="name_details").count(),
        "possible_groups": groups.filter(match_type="similar_name").count(),
        "recent_groups": (
            groups.filter(status="open")
            .annotate(candidate_count=Count("candidates"))
            .order_by("-created_at")[:8]
        ),
    }

    return render(
        request,
        "duplicates/dashboard.html",
        context,
    )


@login_required
def duplicate_group_list(request):
    groups = (
        DuplicateGroup.objects
        .annotate(candidate_count=Count("candidates"))
        .order_by("-created_at")
    )

    status = request.GET.get("status", "open")
    match_type = request.GET.get("match_type", "")
    search = request.GET.get("q", "").strip()

    valid_statuses = {"open", "resolved", "dismissed"}

    if status in valid_statuses:
        groups = groups.filter(status=status)
    elif status != "all":
        status = "open"
        groups = groups.filter(status="open")

    if match_type:
        groups = groups.filter(match_type=match_type)

    if search:
        groups = groups.filter(
            Q(description__icontains=search)
            | Q(candidates__employee__full_name__icontains=search)
            | Q(candidates__employee__employee_number__icontains=search)
            | Q(candidates__employee__designation__icontains=search)
            | Q(candidates__employee__station__icontains=search)
        ).distinct()

    paginator = Paginator(groups, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "groups": page_obj.object_list,
        "selected_status": status,
        "selected_match_type": match_type,
        "search_query": search,
        "match_types": DuplicateGroup.MATCH_TYPE_CHOICES,
    }

    return render(
        request,
        "duplicates/group_list.html",
        context,
    )


@login_required
def duplicate_group_detail(request, pk):
    group = get_object_or_404(
        DuplicateGroup.objects.prefetch_related(
            "candidates__employee",
            "resolutions__performed_by",
        ),
        pk=pk,
    )

    candidates = list(
        group.candidates.select_related("employee").all()
    )

    # Prepare comparison information for every employee.
    for candidate in candidates:
        employee = candidate.employee

        candidate.source_records = (
            candidate.evidence.get("source_records", [])
            if isinstance(candidate.evidence, dict)
            else []
        )

        candidate.employee_record = {
            "id": employee.pk,
            "name": employee.full_name,
            "serial_number": employee.serial_number,
            "employee_number": employee.employee_number,
            "gender": employee.gender,
            "designation": employee.designation,
            "job_group": employee.job_group,
            "appointment_type": employee.appointment_type,
            "station": employee.station,
            "date_of_arrival": employee.date_of_arrival,
            "phone_number": employee.phone_number,
            "ethnicity": employee.ethnicity,
            "status": employee.status,
            "remark": employee.remark,
            "is_archived": employee.is_archived,
        }

    context = {
        "group": group,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "resolutions": group.resolutions.all(),
        "can_resolve": group.status == "open",
    }

    return render(
        request,
        "duplicates/group_detail.html",
        context,
    )


@login_required
@require_POST
@transaction.atomic
def resolve_duplicate_group(request, pk):
    group = get_object_or_404(
        DuplicateGroup.objects.select_for_update(),
        pk=pk,
    )

    if group.status != "open":
        messages.warning(
            request,
            "This duplicate group has already been reviewed.",
        )
        return redirect(
            "duplicates:group_detail",
            pk=group.pk,
        )

    action = request.POST.get("action", "").strip()
    notes = request.POST.get("notes", "").strip()

    valid_actions = {
        "archive_others",
        "keep_both",
        "not_duplicate",
    }

    if action not in valid_actions:
        messages.error(request, "Please select a valid resolution.")
        return redirect(
            "duplicates:group_detail",
            pk=group.pk,
        )

    candidates = list(
        DuplicateCandidate.objects
        .select_for_update()
        .select_related("employee")
        .filter(group=group)
    )

    if len(candidates) < 2:
        messages.error(
            request,
            "This group does not contain enough employee records to resolve.",
        )
        return redirect(
            "duplicates:group_detail",
            pk=group.pk,
        )

    retained_employee = None

    if action == "archive_others":
        retained_id = request.POST.get("retained_employee")

        retained_candidate = next(
            (
                candidate for candidate in candidates
                if str(candidate.employee_id) == retained_id
            ),
            None,
        )

        if retained_candidate is None:
            messages.error(
                request,
                "Select a valid employee record from this group.",
            )
            return redirect(
                "duplicates:group_detail",
                pk=group.pk,
            )

        retained_employee = retained_candidate.employee

    snapshot = {
        "group_id": group.pk,
        "match_type": group.match_type,
        "confidence": str(group.confidence),
        "description": group.description,
        "candidates": [
            {
                "employee_id": candidate.employee_id,
                "employee_number": candidate.employee.employee_number,
                "serial_number": candidate.employee.serial_number,
                "full_name": candidate.employee.full_name,
                "designation": candidate.employee.designation,
                "station": candidate.employee.station,
                "was_archived": candidate.employee.is_archived,
                "source_records": candidate.evidence.get(
                    "source_records", []
                ) if isinstance(candidate.evidence, dict) else [],
            }
            for candidate in candidates
        ],
    }

    if action == "archive_others":

        for candidate in candidates:
            employee = candidate.employee

            candidate.is_retained = (
                employee.pk == retained_employee.pk
            )
            candidate.save(update_fields=["is_retained"])

            if employee.pk != retained_employee.pk:
                employee.is_archived = True
                employee.save(
                    update_fields=["is_archived", "updated_at"]
                )

        group.status = "resolved"

    elif action == "keep_both":

        for candidate in candidates:
            candidate.is_retained = False
            candidate.save(update_fields=["is_retained"])

        group.status = "resolved"

    elif action == "not_duplicate":

        for candidate in candidates:
            candidate.is_retained = False
            candidate.save(update_fields=["is_retained"])

        group.status = "dismissed"

    DuplicateResolution.objects.create(
        group=group,
        action=action,
        retained_employee=retained_employee,
        performed_by=request.user,
        notes=notes,
        decision_snapshot=snapshot,
    )

    group.reviewed_at = timezone.now()
    group.save(
        update_fields=["status", "reviewed_at", "updated_at"]
    )

    messages.success(
        request,
        "Duplicate group reviewed and the decision has been recorded.",
    )

    return redirect(
        "duplicates:group_detail",
        pk=group.pk,
    )


@login_required
@require_POST
@transaction.atomic
def archive_duplicate_employee(request, group_pk, employee_pk):
    """
    Archive one employee from a duplicate group without
    permanently deleting the employee record.
    """

    group = get_object_or_404(
        DuplicateGroup.objects.select_for_update(),
        pk=group_pk,
    )

    if group.status != "open":
        messages.error(
            request,
            "Only open duplicate groups can be modified.",
        )
        return redirect(
            "duplicates:group_detail",
            pk=group.pk,
        )

    candidate = get_object_or_404(
        DuplicateCandidate.objects.select_related("employee"),
        group=group,
        employee_id=employee_pk,
    )

    employee = candidate.employee

    if employee.is_archived:
        messages.info(
            request,
            "This employee is already archived.",
        )
        return redirect(
            "duplicates:group_detail",
            pk=group.pk,
        )

    # Do not archive the last active record in a group.
    active_candidates = group.candidates.filter(
        employee__is_archived=False
    ).count()

    if active_candidates <= 1:
        messages.error(
            request,
            "You cannot archive the last active employee in this group.",
        )
        return redirect(
            "duplicates:group_detail",
            pk=group.pk,
        )

    employee.is_archived = True
    employee.save(
        update_fields=["is_archived", "updated_at"]
    )

    messages.success(
        request,
        f"{employee.full_name} has been archived. The record can be restored later.",
    )

    return redirect(
        "duplicates:group_detail",
        pk=group.pk,
    )
