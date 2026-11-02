from collections import Counter
from datetime import datetime

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.employees.models import Employee
from apps.duplicates.models import DuplicateGroup
from .forms import ProfileForm


User = get_user_model()


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
        if field_name == "gender" and key in ("female", "male"):
            label = key.title()
        else:
            label = max(labels[key], key=labels[key].get)

        results.append({"label": label, "count": count})

    results.sort(key=lambda item: (-item["count"], item["label"].casefold()))
    return results[:limit] if limit else results


def build_arrival_trend(queryset):
    """Count employee arrivals by month."""
    counts = Counter()

    for arrival_date in queryset.values_list("date_of_arrival", flat=True):
        if arrival_date:
            counts[arrival_date.strftime("%Y-%m")] += 1

    ordered_months = sorted(counts)
    return {
        "labels": [
            datetime.strptime(month, "%Y-%m").strftime("%b %Y")
            for month in ordered_months
        ],
        "data": [counts[month] for month in ordered_months],
    }


@login_required
def dashboard(request):
    all_employees = Employee.objects.all()
    active_employees = all_employees.filter(is_archived=False)
    archived_employees = all_employees.filter(is_archived=True)

    gender_data = build_distribution(active_employees, "gender")
    job_group_data = build_distribution(active_employees, "job_group", limit=10)
    station_data = build_distribution(active_employees, "station", limit=10)
    appointment_data = build_distribution(active_employees, "appointment_type")
    status_data = build_distribution(active_employees, "status")
    arrival_trend = build_arrival_trend(active_employees)

    context = {
        "total_employees": active_employees.count(),
        "active_employees": active_employees.count(),
        "archived_employees": archived_employees.count(),
        "total_stations": len(build_distribution(active_employees, "station")),
        "pending_duplicates": DuplicateGroup.objects.filter(status="open").count(),
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
        "recent_employees": active_employees.order_by("-created_at")[:8],
    }

    return render(request, "dashboard/index.html", context)


@login_required
def profile(request):
    """View and update the signed-in user's own profile."""
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect("profile")
    else:
        form = ProfileForm(instance=request.user)

    return render(request, "accounts/profile.html", {"form": form})


@login_required
def change_password(request):
    """Change the signed-in user's password and keep their session active."""
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Your password has been changed.")
            return redirect("profile")
    else:
        form = PasswordChangeForm(request.user)

    return render(request, "accounts/change_password.html", {"form": form})


def is_superuser(user):
    return user.is_authenticated and user.is_superuser


@user_passes_test(is_superuser)
def user_management(request):
    """List existing accounts. Account creation is intentionally not provided."""
    query = request.GET.get("q", "").strip()
    users = User.objects.all().order_by("username")

    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )

    return render(
        request,
        "accounts/user_management.html",
        {"users": users, "search_query": query},
    )


@user_passes_test(is_superuser)
def toggle_user_active(request, user_id):
    """Activate/deactivate another account; never allow self-lockout."""
    if request.method != "POST":
        return redirect("user_management")

    target = get_object_or_404(User, pk=user_id)

    if target.pk == request.user.pk:
        messages.error(request, "You cannot deactivate your own account here.")
        return redirect("user_management")

    if target.is_superuser:
        messages.error(request, "Superuser accounts cannot be deactivated here.")
        return redirect("user_management")

    target.is_active = not target.is_active
    target.save(update_fields=["is_active"])

    state = "activated" if target.is_active else "deactivated"
    messages.success(request, f"{target.username} has been {state}.")
    return redirect("user_management")


@user_passes_test(is_superuser)
def reset_user_password(request, user_id):
    """Allow a superuser to set a new password for an existing account."""
    target = get_object_or_404(User, pk=user_id)

    if target.is_superuser:
        messages.error(request, "This screen cannot reset a superuser password.")
        return redirect("user_management")

    if request.method == "POST":
        form = SetPasswordForm(target, request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"Password updated for {target.username}.",
            )
            return redirect("user_management")
    else:
        form = SetPasswordForm(target)

    return render(
        request,
        "accounts/reset_user_password.html",
        {"form": form, "target_user": target},
    )
