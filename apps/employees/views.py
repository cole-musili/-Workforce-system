
from collections import Counter

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .models import Employee
from .forms import EmployeeForm


def normalized_filter_options(queryset, field_name):
    """
    Return unique, consistently formatted filter options.

    Values differing only by capitalization or surrounding/
    repeated whitespace are treated as one option.

    The most frequently used original spelling is retained,
    except for gender, which uses standard Female/Male labels.
    """
    values = queryset.exclude(
        **{f"{field_name}__isnull": True}
    ).exclude(
        **{f"{field_name}__exact": ""}
    ).values_list(field_name, flat=True)

    counts = Counter()
    original_values = {}

    for value in values:
        if value is None:
            continue

        cleaned = " ".join(str(value).split())

        if not cleaned:
            continue

        key = cleaned.casefold()

        counts[key] += 1

        original_values.setdefault(key, Counter())
        original_values[key][cleaned] += 1

    options = []

    for key, count in counts.items():

        if field_name == "gender":
            if key == "female":
                display_value = "Female"
            elif key == "male":
                display_value = "Male"
            else:
                display_value = max(
                    original_values[key],
                    key=lambda value: (
                        original_values[key][value],
                        value.casefold(),
                    ),
                )
        else:
            display_value = max(
                original_values[key],
                key=lambda value: (
                    original_values[key][value],
                    value.casefold(),
                ),
            )

        options.append(display_value)

    return sorted(options, key=str.casefold)


@login_required
def employee_list(request):
    active_employees = Employee.objects.filter(
        is_archived=False
    )

    employees = active_employees.order_by(
        "full_name"
    )

    query = request.GET.get("q", "").strip()
    gender = request.GET.get("gender", "").strip()
    job_group = request.GET.get("job_group", "").strip()
    appointment = request.GET.get("appointment", "").strip()
    status = request.GET.get("status", "").strip()
    station = request.GET.get("station", "").strip()

    if query:
        employees = employees.filter(
            Q(full_name__icontains=query)
            | Q(employee_number__icontains=query)
            | Q(designation__icontains=query)
            | Q(station__icontains=query)
            | Q(phone_number__icontains=query)
            | Q(job_group__icontains=query)
            | Q(appointment_type__icontains=query)
        )

    if gender:
        employees = employees.filter(
            gender__iexact=gender
        )

    if job_group:
        employees = employees.filter(
            job_group__iexact=job_group
        )

    if appointment:
        employees = employees.filter(
            appointment_type__iexact=appointment
        )

    if status:
        employees = employees.filter(
            status__iexact=status
        )

    if station:
        employees = employees.filter(
            station__iexact=station
        )

    paginator = Paginator(employees, 20)
    page_obj = paginator.get_page(
        request.GET.get("page")
    )

    context = {
        "page_obj": page_obj,
        "employees": page_obj.object_list,

        "query": query,
        "gender": gender,
        "job_group": job_group,
        "appointment": appointment,
        "status": status,
        "station": station,

        "genders": normalized_filter_options(
            active_employees,
            "gender",
        ),

        "job_groups": normalized_filter_options(
            active_employees,
            "job_group",
        ),

        "appointments": normalized_filter_options(
            active_employees,
            "appointment_type",
        ),

        "statuses": normalized_filter_options(
            active_employees,
            "status",
        ),

        "stations": normalized_filter_options(
            active_employees,
            "station",
        ),
    }

    return render(
        request,
        "employees/list.html",
        context,
    )


@login_required
def employee_detail(request, pk):
    employee = get_object_or_404(
        Employee,
        pk=pk,
        is_archived=False
    )

    return render(
        request,
        "employees/detail.html",
        {"employee": employee}
    )


@login_required
def employee_create(request):
    if request.method == "POST":
        form = EmployeeForm(request.POST)

        if form.is_valid():
            employee = form.save()

            messages.success(
                request,
                f"{employee.full_name} was added successfully."
            )

            return redirect(
                "employee_detail",
                pk=employee.pk
            )
    else:
        form = EmployeeForm()

    return render(
        request,
        "employees/form.html",
        {
            "form": form,
            "title": "Add employee",
        }
    )


@login_required
def employee_update(request, pk):
    employee = get_object_or_404(
        Employee,
        pk=pk,
        is_archived=False
    )

    if request.method == "POST":
        form = EmployeeForm(
            request.POST,
            instance=employee
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Employee information updated successfully."
            )

            return redirect(
                "employee_detail",
                pk=employee.pk
            )
    else:
        form = EmployeeForm(instance=employee)

    return render(
        request,
        "employees/form.html",
        {
            "form": form,
            "title": "Edit employee",
            "employee": employee,
        }
    )


@login_required
def employee_archive(request, pk):
    employee = get_object_or_404(
        Employee,
        pk=pk,
        is_archived=False
    )

    if request.method == "POST":
        employee.is_archived = True

        employee.save(
            update_fields=[
                "is_archived",
                "updated_at",
            ]
        )

        messages.success(
            request,
            f"{employee.full_name} was archived successfully."
        )

        return redirect("employee_list")

    return render(
        request,
        "employees/archive_confirm.html",
        {"employee": employee}
    )


@login_required
def archived_employee_list(request):
    employees = Employee.objects.filter(
        is_archived=True
    ).order_by("full_name")

    query = request.GET.get("q", "").strip()

    if query:
        employees = employees.filter(
            Q(full_name__icontains=query)
            | Q(employee_number__icontains=query)
            | Q(designation__icontains=query)
            | Q(station__icontains=query)
            | Q(phone_number__icontains=query)
        )

    paginator = Paginator(employees, 20)
    page_obj = paginator.get_page(
        request.GET.get("page")
    )

    context = {
        "page_obj": page_obj,
        "employees": page_obj.object_list,
        "query": query,
        "archived_count": Employee.objects.filter(
            is_archived=True
        ).count(),
    }

    return render(
        request,
        "employees/archived_list.html",
        context
    )


@login_required
@require_POST
def employee_restore(request, pk):
    employee = get_object_or_404(
        Employee,
        pk=pk,
        is_archived=True
    )

    employee.is_archived = False

    try:
        employee.save(
            update_fields=[
                "is_archived",
                "updated_at",
            ]
        )
    except Exception:
        messages.error(
            request,
            "The employee could not be restored. Please check the record and try again."
        )
        return redirect("archived_employee_list")

    messages.success(
        request,
        f"{employee.full_name} has been restored to the active directory."
    )

    return redirect("archived_employee_list")
