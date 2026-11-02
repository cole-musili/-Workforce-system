
import hashlib
import re
import unicodedata

from collections import defaultdict
from decimal import Decimal

from django.db import transaction

from apps.employees.models import Employee
from apps.imports.models import ImportRow
from apps.duplicates.models import (
    DuplicateGroup,
    DuplicateCandidate,
)


def normalize_value(value):
    if value is None:
        return ""

    value = unicodedata.normalize("NFKC", str(value))
    value = value.strip().casefold()
    value = re.sub(r"\s+", " ", value)

    return value


def normalize_identifier(value):
    value = normalize_value(value)

    if not value or value in {"none", "null", "nan"}:
        return ""

    return re.sub(r"\s+", "", value)


def normalize_custom_identifier(custom_data):
    if not isinstance(custom_data, dict):
        return ""

    possible_keys = {
        "national_id",
        "id_no",
        "id/no",
        "id number",
        "national id",
    }

    for key, value in custom_data.items():
        normalized_key = normalize_value(key).replace("_", " ")

        if normalized_key in possible_keys:
            return normalize_identifier(value)

    return ""


def create_fingerprint(match_type, employee_ids):
    employee_ids = sorted(set(employee_ids))

    payload = f"{match_type}:{','.join(map(str, employee_ids))}"

    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()


def get_employee_import_sources(employee_ids):
    """
    Retrieve all known import origins for the supplied employees.

    One employee can have multiple source rows across different
    worksheets or import batches.
    """

    sources = defaultdict(list)

    import_rows = (
        ImportRow.objects
        .filter(employee_id__in=employee_ids)
        .select_related("batch")
        .order_by("batch__uploaded_at", "source_sheet", "source_row_number")
    )

    for row in import_rows:
        sources[row.employee_id].append({
            "batch_id": row.batch_id,
            "filename": row.batch.filename,
            "uploaded_at": (
                row.batch.uploaded_at.isoformat()
                if row.batch.uploaded_at else None
            ),
            "source_sheet": row.source_sheet,
            "source_period": row.source_period,
            "source_row_number": row.source_row_number,
            "import_result": row.result,
        })

    return sources


def collect_matches(employees):
    matches = []

    identifier_groups = defaultdict(list)
    national_id_groups = defaultdict(list)
    detail_groups = defaultdict(list)
    name_groups = defaultdict(list)

    for employee in employees:

        employee_number = normalize_identifier(
            employee.employee_number
        )

        national_id = normalize_custom_identifier(
            employee.custom_data
        )

        name = normalize_value(employee.full_name)
        designation = normalize_value(employee.designation)
        station = normalize_value(employee.station)

        if employee_number:
            identifier_groups[employee_number].append(employee)

        if national_id:
            national_id_groups[national_id].append(employee)

        if name and designation and station:
            detail_groups[
                (name, designation, station)
            ].append(employee)

        if name:
            name_groups[name].append(employee)

    def add_groups(groups, match_type, confidence, description):

        for key, records in groups.items():

            if len(records) < 2:
                continue

            employee_ids = [
                employee.pk for employee in records
            ]

            matches.append({
                "match_type": match_type,
                "confidence": Decimal(str(confidence)),
                "description": description,
                "evidence": {
                    "matching_value": str(key),
                    "employee_ids": employee_ids,
                    "record_count": len(records),
                },
                "employees": records,
            })

    add_groups(
        identifier_groups,
        "employee_number",
        100,
        "Matching employee numbers.",
    )

    add_groups(
        national_id_groups,
        "national_id",
        100,
        "Matching National ID values.",
    )

    add_groups(
        detail_groups,
        "name_details",
        90,
        "Matching employee name, designation and station.",
    )

    add_groups(
        name_groups,
        "similar_name",
        65,
        "Matching employee names. Other details require manual comparison.",
    )

    return matches


@transaction.atomic
def scan_duplicates(include_archived=False):

    employees_queryset = Employee.objects.all().order_by("pk")

    if not include_archived:
        employees_queryset = employees_queryset.filter(
            is_archived=False
        )

    employees = list(employees_queryset)

    detected_matches = collect_matches(employees)

    all_employee_ids = {
        employee.pk
        for match in detected_matches
        for employee in match["employees"]
    }

    # Fetch import provenance once, avoiding repeated queries.
    import_sources = get_employee_import_sources(
        all_employee_ids
    )

    created_groups = 0
    updated_groups = 0
    created_candidates = 0
    updated_candidates = 0

    for match in detected_matches:

        matched_employees = match["employees"]

        employee_ids = [
            employee.pk
            for employee in matched_employees
        ]

        fingerprint = create_fingerprint(
            match["match_type"],
            employee_ids,
        )

        group_evidence = dict(match["evidence"])

        group_evidence["employee_sources"] = {
            str(employee.pk): import_sources.get(
                employee.pk, []
            )
            for employee in matched_employees
        }

        group, created = DuplicateGroup.objects.get_or_create(
            fingerprint=fingerprint,
            defaults={
                "match_type": match["match_type"],
                "confidence": match["confidence"],
                "description": match["description"],
                "detection_evidence": group_evidence,
                "status": "open",
            },
        )

        if created:
            created_groups += 1

        elif group.status == "open":
            group.confidence = match["confidence"]
            group.description = match["description"]
            group.detection_evidence = group_evidence

            group.save(update_fields=[
                "confidence",
                "description",
                "detection_evidence",
                "updated_at",
            ])

            updated_groups += 1

        # Do not overwrite previously reviewed decisions.
        if group.status != "open":
            continue

        for employee in matched_employees:

            candidate_evidence = {
                "match_type": match["match_type"],
                "employee_number": employee.employee_number,
                "serial_number": employee.serial_number,
                "full_name": employee.full_name,
                "designation": employee.designation,
                "station": employee.station,
                "source_records": import_sources.get(
                    employee.pk, []
                ),
            }

            candidate, candidate_created = (
                DuplicateCandidate.objects.get_or_create(
                    group=group,
                    employee=employee,
                    defaults={
                        "match_basis": match["description"],
                        "confidence": match["confidence"],
                        "evidence": candidate_evidence,
                    },
                )
            )

            if candidate_created:
                created_candidates += 1

            else:
                # Refresh evidence for candidates created by
                # earlier scans, without changing retention decisions.
                candidate.match_basis = match["description"]
                candidate.confidence = match["confidence"]
                candidate.evidence = candidate_evidence

                candidate.save(update_fields=[
                    "match_basis",
                    "confidence",
                    "evidence",
                ])

                updated_candidates += 1

    return {
        "employees_scanned": len(employees),
        "matches_detected": len(detected_matches),
        "groups_created": created_groups,
        "groups_updated": updated_groups,
        "candidates_created": created_candidates,
        "candidates_updated": updated_candidates,
    }
