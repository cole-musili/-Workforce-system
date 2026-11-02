
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db.models.functions import ExtractMonth, ExtractYear
from django.shortcuts import render

from apps.employees.models import Employee


@login_required
def analytics_dashboard(request):
    """
    Workforce analytics dashboard.

    Excludes archived employees from active workforce statistics.
    """

    employees = Employee.objects.filter(is_archived=False)

    # --------------------------------------------------
    # Workforce overview
    # --------------------------------------------------

    total_employees = employees.count()

    archived_employees = Employee.objects.filter(
        is_archived=True
    ).count()

    # --------------------------------------------------
    # Workforce composition
    # --------------------------------------------------

    gender_distribution = list(
        employees.exclude(gender__isnull=True)
        .exclude(gender__exact="")
        .values("gender")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    appointment_distribution = list(
        employees.exclude(appointment_type__isnull=True)
        .exclude(appointment_type__exact="")
        .values("appointment_type")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    designation_distribution = list(
        employees.exclude(designation__isnull=True)
        .exclude(designation__exact="")
        .values("designation")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    job_group_distribution = list(
        employees.exclude(job_group__isnull=True)
        .exclude(job_group__exact="")
        .values("job_group")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    station_distribution = list(
        employees.exclude(station__isnull=True)
        .exclude(station__exact="")
        .values("station")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    ethnicity_distribution = list(
        employees.exclude(ethnicity__isnull=True)
        .exclude(ethnicity__exact="")
        .values("ethnicity")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    # --------------------------------------------------
    # Recruitment / arrival trends
    # --------------------------------------------------

    arrival_by_year = list(
        employees.filter(date_of_arrival__isnull=False)
        .annotate(year=ExtractYear("date_of_arrival"))
        .values("year")
        .annotate(total=Count("id"))
        .order_by("year")
    )

    arrival_by_month = list(
        employees.filter(date_of_arrival__isnull=False)
        .annotate(
            year=ExtractYear("date_of_arrival"),
            month=ExtractMonth("date_of_arrival"),
        )
        .values("year", "month")
        .annotate(total=Count("id"))
        .order_by("year", "month")
    )

    # --------------------------------------------------
    # Data quality statistics
    # --------------------------------------------------

    employees_with_arrival_date = employees.filter(
        date_of_arrival__isnull=False
    ).count()

    employees_without_arrival_date = employees.filter(
        date_of_arrival__isnull=True
    ).count()

    employees_with_phone = employees.exclude(
        phone_number__isnull=True
    ).exclude(phone_number__exact="").count()

    employees_without_phone = (
        total_employees - employees_with_phone
    )

    employees_with_designation = employees.exclude(
        designation__isnull=True
    ).exclude(designation__exact="").count()

    employees_without_designation = (
        total_employees - employees_with_designation
    )

    # --------------------------------------------------
    # Recent employee records
    # --------------------------------------------------

    recent_employees = employees.order_by(
        "-created_at"
    )[:10]

    # --------------------------------------------------
    # Chart data
    # Pass dictionaries directly to json_script in template.
    # Do not use json.dumps() here.
    # --------------------------------------------------

    gender_chart = {
        "labels": [
            item["gender"]
            for item in gender_distribution
        ],
        "data": [
            item["total"]
            for item in gender_distribution
        ],
    }

    appointment_chart = {
        "labels": [
            item["appointment_type"]
            for item in appointment_distribution
        ],
        "data": [
            item["total"]
            for item in appointment_distribution
        ],
    }

    station_chart = {
        "labels": [
            item["station"]
            for item in station_distribution
        ],
        "data": [
            item["total"]
            for item in station_distribution
        ],
    }

    designation_chart = {
        "labels": [
            item["designation"]
            for item in designation_distribution
        ],
        "data": [
            item["total"]
            for item in designation_distribution
        ],
    }

    job_group_chart = {
        "labels": [
            item["job_group"]
            for item in job_group_distribution
        ],
        "data": [
            item["total"]
            for item in job_group_distribution
        ],
    }

    ethnicity_chart = {
        "labels": [
            item["ethnicity"]
            for item in ethnicity_distribution
        ],
        "data": [
            item["total"]
            for item in ethnicity_distribution
        ],
    }

    arrival_year_chart = {
        "labels": [
            str(item["year"])
            for item in arrival_by_year
        ],
        "data": [
            item["total"]
            for item in arrival_by_year
        ],
    }

    # --------------------------------------------------
    # Dashboard context
    # --------------------------------------------------

    context = {
        "total_employees": total_employees,
        "archived_employees": archived_employees,

        "gender_distribution": gender_distribution,
        "appointment_distribution": appointment_distribution,
        "designation_distribution": designation_distribution,
        "job_group_distribution": job_group_distribution,
        "station_distribution": station_distribution,
        "ethnicity_distribution": ethnicity_distribution,

        "arrival_by_year": arrival_by_year,
        "arrival_by_month": arrival_by_month,

        "employees_with_arrival_date": employees_with_arrival_date,
        "employees_without_arrival_date": employees_without_arrival_date,

        "employees_with_phone": employees_with_phone,
        "employees_without_phone": employees_without_phone,

        "employees_with_designation": employees_with_designation,
        "employees_without_designation": employees_without_designation,

        "recent_employees": recent_employees,

        # Chart datasets
        "gender_chart": gender_chart,
        "appointment_chart": appointment_chart,
        "station_chart": station_chart,
        "designation_chart": designation_chart,
        "job_group_chart": job_group_chart,
        "ethnicity_chart": ethnicity_chart,
        "arrival_year_chart": arrival_year_chart,
    }

    return render(
        request,
        "analytics/dashboard.html",
        context,
    )
