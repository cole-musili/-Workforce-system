
from collections import Counter
from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.employees.models import Employee
from apps.duplicates.models import DuplicateGroup


def build_distribution(queryset, field_name, limit=None):
    """Build case-insensitive distribution data for dashboard charts."""

    counts = Counter()
    labels = {}

    for value in queryset.values_list(field_name, flat=True):
        if not value:
            continue

        cleaned = " ".join(str(value).split())

        if not cleaned:
            continue

        key = cleaned.casefold()
        counts[key] += 1

        labels.setdefault(key, Counter())
        labels[key][cleaned] += 1

    results = []

    for key, count in counts.items():
        if field_name == "gender":
            if key == "female":
                label = "Female"
            elif key == "male":
                label = "Male"
            else:
                label = max(labels[key], key=labels[key].get)
        else:
            label = max(labels[key], key=labels[key].get)

        results.append({
            "label": label,
            "count": count,
        })

    results.sort(
        key=lambda item: (-item["count"], item["label"].casefold())
    )

    return results[:limit] if limit else results


def build_arrival_trend(queryset):
    """Count employee arrivals by month."""

    counts = Counter()

    for arrival_date in queryset.values_list(
        "date_of_arrival",
        flat=True,
    ):
        if arrival_date:
            counts[arrival_date.strftime("%Y-%m")] += 1

    ordered_months = sorted(counts)

    return {
        "labels": [
            datetime.strptime(month, "%Y-%m").strftime("%b %Y")
            for month in ordered_months
        ],
        "data": [
            counts[month] for month in ordered_months
        ],
    }


@login_required
def dashboard(request):

    all_employees = Employee.objects.all()

    active_employees = all_employees.filter(
        is_archived=False
    )

    archived_employees = all_employees.filter(
        is_archived=True
    )

    gender_data = build_distribution(
        active_employees,
        "gender",
    )

    job_group_data = build_distribution(
        active_employees,
        "job_group",
        limit=10,
    )

    station_data = build_distribution(
        active_employees,
        "station",
        limit=10,
    )

    appointment_data = build_distribution(
        active_employees,
        "appointment_type",
    )

    status_data = build_distribution(
        active_employees,
        "status",
    )

    arrival_trend = build_arrival_trend(
        active_employees
    )

    context = {
        "total_employees": active_employees.count(),
        "active_employees": active_employees.count(),
        "archived_employees": archived_employees.count(),

        "total_stations": len(
            build_distribution(active_employees, "station")
        ),

        "pending_duplicates": DuplicateGroup.objects.filter(
            status="open"
        ).count(),

        # Pass Python objects directly to json_script.
        "gender_chart_json": gender_data,
        "job_group_chart_json": job_group_data,
        "station_chart_json": station_data,
        "appointment_chart_json": appointment_data,
        "status_chart_json": status_data,
        "arrival_chart_json": arrival_trend,

        "gender_data": gender_data,
        "job_group_data": job_group_data,
        "station_data": station_data,
        "appointment_data": appointment_data,
        "status_data": status_data,
        "arrival_trend": arrival_trend,

        "recent_employees": active_employees.order_by(
            "-created_at"
        )[:8],
    }

    return render(
        request,
        "dashboard/index.html",
        context,
    )
