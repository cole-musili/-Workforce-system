
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db.models.functions import Trim
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from apps.employees.models import Employee


REPORT_TYPES = {
    "employee_register": "Employee Register",
    "new_employees": "New Employees",
    "station": "Establishment by Station",
    "appointment": "Appointment Analysis",
    "gender": "Gender Analysis",
    "data_quality": "Data Quality Report",
}


EMPLOYEE_COLUMNS = [
    ("S/NO", "serial_number"),
    ("P/No.", "employee_number"),
    ("Employee Name", "full_name"),
    ("Gender", "gender"),
    ("Designation", "designation"),
    ("Job Group", "job_group"),
    ("Appointment Type", "appointment_type"),
    ("Date of Arrival", "date_of_arrival"),
    ("Contract Period", "contract_period"),
    ("Station", "station"),
    ("Phone Number", "phone_number"),
    ("Ethnicity", "ethnicity"),
    ("Status", "status"),
]


# Station labels are displayed consistently even when source records use
# different capitalization or contain accidental surrounding spaces.
STATION_LABELS = {
    "cgtrh": "CGTRH",
    "county": "County",
    "ahf": "AHF",
}


def station_key(value):
    return (value or "").strip().casefold()


def get_station_aggregates(employees):
    counts = {}
    labels = {}

    for value in employees.values_list("station", flat=True).iterator():
        key = station_key(value)
        counts[key] = counts.get(key, 0) + 1

        if key not in labels:
            labels[key] = (
                STATION_LABELS.get(key)
                or ((value or "").strip() if key else "Not stated")
            )

    results = [
        {"station": labels[key], "total": total}
        for key, total in counts.items()
    ]
    return sorted(
        results,
        key=lambda item: (-item["total"], item["station"].casefold()),
    )


def get_station_choices(employees):
    return [
        item["station"]
        for item in get_station_aggregates(employees)
        if item["station"] != "Not stated"
    ]


def get_normalized_text_aggregates(employees, field):
    """Group text values without case or surrounding-space differences."""
    counts = {}
    labels = {}

    for value in employees.values_list(field, flat=True).iterator():
        clean_value = (value or "").strip()
        key = clean_value.casefold()
        counts[key] = counts.get(key, 0) + 1

        if key not in labels:
            if not key:
                labels[key] = "Not stated"
            elif field == "appointment_type":
                labels[key] = clean_value.title()
            else:
                # Preserve job-group codes and their original formatting.
                labels[key] = clean_value

    results = [
        {field: labels[key], "total": total}
        for key, total in counts.items()
    ]
    return sorted(
        results,
        key=lambda item: (-item["total"], str(item[field]).casefold()),
    )


def get_normalized_text_choices(employees, field):
    return [
        item[field]
        for item in get_normalized_text_aggregates(employees, field)
        if item[field] != "Not stated"
    ]


# ------------------------------------------------------
# SHARED FILTERING
# ------------------------------------------------------

def get_filtered_employees(request):
    employee_state = request.GET.get(
        "employee_state", "active"
    ).strip()

    station_filter = request.GET.get("station", "").strip()
    appointment_filter = request.GET.get(
        "appointment_type", ""
    ).strip()
    job_group_filter = request.GET.get("job_group", "").strip()
    status_filter = request.GET.get("status", "").strip()

    if employee_state not in ("active", "archived", "all"):
        employee_state = "active"

    employees = Employee.objects.all()

    if employee_state == "active":
        employees = employees.filter(is_archived=False)
    elif employee_state == "archived":
        employees = employees.filter(is_archived=True)

    if station_filter:
        employees = (
            employees.annotate(_station_clean=Trim("station"))
            .filter(_station_clean__iexact=station_filter.strip())
        )

    if appointment_filter:
        employees = (
            employees.annotate(_appointment_clean=Trim("appointment_type"))
            .filter(_appointment_clean__iexact=appointment_filter.strip())
        )

    if job_group_filter:
        employees = (
            employees.annotate(_job_group_clean=Trim("job_group"))
            .filter(_job_group_clean__iexact=job_group_filter.strip())
        )

    if status_filter:
        employees = employees.filter(status=status_filter)

    filters = {
        "employee_state": employee_state,
        "station": station_filter,
        "appointment_type": appointment_filter,
        "job_group": job_group_filter,
        "status": status_filter,
    }

    return employees, filters


def count_missing_values(employees, field):
    """
    Count missing values safely for both text fields and date fields.

    DateField values should be checked with isnull only. CharFields can be
    missing either as NULL or as an empty string.
    """
    missing = employees.filter(**{f"{field}__isnull": True}).count()

    if field != "date_of_arrival":
        missing += employees.filter(**{f"{field}__exact": ""}).count()

    return missing


def get_filter_description(filters):
    descriptions = [
        f"Employee state: {filters['employee_state'].title()}",
        f"Station: {filters['station'] or 'All stations'}",
        f"Appointment: {filters['appointment_type'] or 'All appointments'}",
        f"Job group: {filters['job_group'] or 'All job groups'}",
        f"Status: {filters['status'] or 'All statuses'}",
    ]

    return descriptions


# ------------------------------------------------------
# DASHBOARD
# ------------------------------------------------------

@login_required
def reports_dashboard(request):
    employees, filters = get_filtered_employees(request)

    total_employees = employees.count()

    female_count = employees.filter(
        gender__iexact="Female"
    ).count()

    male_count = employees.filter(
        gender__iexact="Male"
    ).count()

    with_arrival_date = employees.filter(
        date_of_arrival__isnull=False
    ).count()

    without_arrival_date = employees.filter(
        date_of_arrival__isnull=True
    ).count()

    def distribution(field):
        if field == "station":
            return get_station_aggregates(employees)

        if field in ("appointment_type", "job_group"):
            return get_normalized_text_aggregates(employees, field)

        return list(
            employees.exclude(**{f"{field}__isnull": True})
            .exclude(**{f"{field}__exact": ""})
            .values(field)
            .annotate(total=Count("id"))
            .order_by("-total", field)
        )

    def missing_count(field):
        return count_missing_values(employees, field)

    by_station = distribution("station")
    by_designation = distribution("designation")
    by_job_group = distribution("job_group")
    by_appointment = distribution("appointment_type")
    by_contract = distribution("contract_period")
    by_gender = distribution("gender")
    by_ethnicity = distribution("ethnicity")
    by_status = distribution("status")

    missing_data = [
        {"label": "Employee number (P/No.)", "count": missing_count("employee_number")},
        {"label": "Gender", "count": missing_count("gender")},
        {"label": "Designation", "count": missing_count("designation")},
        {"label": "Job group", "count": missing_count("job_group")},
        {"label": "Appointment type", "count": missing_count("appointment_type")},
        {"label": "Date of arrival", "count": without_arrival_date},
        {"label": "Station", "count": missing_count("station")},
        {"label": "Phone number", "count": missing_count("phone_number")},
        {"label": "Ethnicity", "count": missing_count("ethnicity")},
        {"label": "Employment status", "count": missing_count("status")},
    ]

    recent_employees = employees.order_by("-created_at")[:15]

    filter_employees = Employee.objects.filter(is_archived=False)

    def filter_choices(field):
        if field == "station":
            return get_station_choices(filter_employees)

        if field in ("appointment_type", "job_group"):
            return get_normalized_text_choices(filter_employees, field)

        return list(
            filter_employees
            .exclude(**{f"{field}__isnull": True})
            .exclude(**{f"{field}__exact": ""})
            .values_list(field, flat=True)
            .distinct()
            .order_by(field)
        )

    context = {
        "total_employees": total_employees,
        "female_count": female_count,
        "male_count": male_count,
        "with_arrival_date": with_arrival_date,
        "without_arrival_date": without_arrival_date,

        "by_station": by_station,
        "by_designation": by_designation,
        "by_job_group": by_job_group,
        "by_appointment": by_appointment,
        "by_contract": by_contract,
        "by_gender": by_gender,
        "by_ethnicity": by_ethnicity,
        "by_status": by_status,

        "missing_data": missing_data,
        "recent_employees": recent_employees,

        "station_choices": filter_choices("station"),
        "appointment_choices": filter_choices("appointment_type"),
        "job_group_choices": filter_choices("job_group"),
        "status_choices": filter_choices("status"),

        "filters": filters,
        "report_types": REPORT_TYPES.items(),
        "current_year": timezone.localdate().year,
    }

    return render(request, "reports/dashboard.html", context)


# ------------------------------------------------------
# REPORT DATA PREPARATION
# ------------------------------------------------------

def get_report_data(request):
    """
    Prepare the records and metadata for a selected report.
    """

    employees, filters = get_filtered_employees(request)

    report_type = request.GET.get(
        "report_type", "employee_register"
    ).strip()

    if report_type not in REPORT_TYPES:
        report_type = "employee_register"

    year = request.GET.get("arrival_year", "").strip()

    if not year.isdigit() or len(year) != 4:
        year = str(timezone.localdate().year)

    year = int(year)

    if report_type == "new_employees":
        employees = employees.filter(
            date_of_arrival__year=year
        )

    employees = employees.order_by("full_name", "employee_number")

    return {
        "employees": employees,
        "filters": filters,
        "report_type": report_type,
        "report_title": REPORT_TYPES[report_type],
        "arrival_year": year,
        "total": employees.count(),
        "generated_at": timezone.localtime(),
    }


# ------------------------------------------------------
# EXCEL FORMATTING
# ------------------------------------------------------

def style_excel_sheet(sheet, widths=None):
    header_fill = PatternFill(
        "solid", fgColor="145A40"
    )

    for cell in sheet[1]:
        cell.font = Font(
            bold=True,
            color="FFFFFF",
            size=10,
        )
        cell.fill = header_fill
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.row_dimensions[1].height = 28

    thin_border = Border(
        bottom=Side(style="thin", color="DDE5E0")
    )

    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.border = thin_border
            cell.alignment = Alignment(vertical="center")

    if widths:
        for column, width in widths.items():
            sheet.column_dimensions[column].width = width
    else:
        for column_cells in sheet.columns:
            column_letter = get_column_letter(
                column_cells[0].column
            )

            max_length = max(
                len(str(cell.value or ""))
                for cell in column_cells
            )

            sheet.column_dimensions[column_letter].width = min(
                max(max_length + 3, 13), 35
            )


def add_excel_title(sheet, title, total):
    sheet.merge_cells("A1:D1")
    sheet["A1"] = "WORKFORCE INSIGHTS"
    sheet["A1"].font = Font(
        size=18,
        bold=True,
        color="FFFFFF",
    )
    sheet["A1"].fill = PatternFill(
        "solid", fgColor="145A40"
    )
    sheet["A1"].alignment = Alignment(
        horizontal="center"
    )

    sheet.merge_cells("A2:D2")
    sheet["A2"] = title
    sheet["A2"].font = Font(
        size=14,
        bold=True,
        color="145A40",
    )
    sheet["A2"].alignment = Alignment(
        horizontal="center"
    )

    sheet["A4"] = "Generated"
    sheet["B4"] = timezone.localtime().strftime(
        "%d %B %Y, %H:%M"
    )

    sheet["A5"] = "Matching employees"
    sheet["B5"] = total


def add_excel_filters(sheet, filters, start_row=7):
    sheet.cell(start_row, 1, "APPLIED FILTERS")
    sheet.cell(start_row, 1).font = Font(
        bold=True, color="FFFFFF"
    )
    sheet.cell(start_row, 1).fill = PatternFill(
        "solid", fgColor="145A40"
    )

    for index, description in enumerate(
        get_filter_description(filters),
        start=start_row + 1,
    ):
        sheet.cell(index, 1, description)


def get_aggregate(field, employees):
    if field == "station":
        return [
            {"station": item["station"], "total": item["total"]}
            for item in get_station_aggregates(employees)
        ]

    if field in ("appointment_type", "job_group"):
        return get_normalized_text_aggregates(employees, field)

    return list(
        employees.values(field)
        .annotate(total=Count("id"))
        .order_by("-total", field)
    )


def add_analysis_sheet(workbook, title, field, employees):
    sheet = workbook.create_sheet(title)

    sheet.append([title, "Employees", "Percentage"])

    total = employees.count()

    for item in get_aggregate(field, employees):
        value = item[field] or "Not stated"
        count = item["total"]

        percentage = (
            round(count / total * 100, 2)
            if total else 0
        )

        sheet.append([value, count, percentage / 100])

    for row in range(2, sheet.max_row + 1):
        sheet.cell(row, 3).number_format = "0.00%"

    style_excel_sheet(
        sheet,
        {"A": 35, "B": 18, "C": 18},
    )

    return sheet


def build_excel_report(data):
    employees = data["employees"]
    report_type = data["report_type"]

    workbook = Workbook()
    summary = workbook.active
    summary.title = "Report Summary"

    add_excel_title(
        summary,
        data["report_title"],
        data["total"],
    )

    add_excel_filters(summary, data["filters"])

    if report_type == "new_employees":
        summary["A14"] = "Arrival year"
        summary["B14"] = data["arrival_year"]

    if report_type == "employee_register":
        sheet = workbook.create_sheet("Employee Register")
        sheet.append([column[0] for column in EMPLOYEE_COLUMNS])

        for employee in employees.iterator():
            values = [
                getattr(employee, field, None)
                for _, field in EMPLOYEE_COLUMNS
            ]

            sheet.append(values)

        for row in sheet.iter_rows(min_row=2):
            row[7].number_format = "dd mmm yyyy"

        style_excel_sheet(sheet, {
            "A": 10,
            "B": 18,
            "C": 30,
            "D": 14,
            "E": 28,
            "F": 15,
            "G": 22,
            "H": 18,
            "I": 18,
            "J": 22,
            "K": 20,
            "L": 20,
            "M": 18,
        })

    elif report_type == "new_employees":
        sheet = workbook.create_sheet("New Employees")
        sheet.append([column[0] for column in EMPLOYEE_COLUMNS])

        for employee in employees.iterator():
            sheet.append([
                getattr(employee, field, None)
                for _, field in EMPLOYEE_COLUMNS
            ])

        for row in sheet.iter_rows(min_row=2):
            row[7].number_format = "dd mmm yyyy"

        style_excel_sheet(sheet)

    elif report_type == "station":
        add_analysis_sheet(
            workbook, "Station Summary", "station", employees
        )

        add_analysis_sheet(
            workbook, "Designation", "designation", employees
        )

    elif report_type == "appointment":
        add_analysis_sheet(
            workbook,
            "Appointment Summary",
            "appointment_type",
            employees,
        )

        add_analysis_sheet(
            workbook,
            "Job Groups",
            "job_group",
            employees,
        )

        add_analysis_sheet(
            workbook,
            "Contract Periods",
            "contract_period",
            employees,
        )

    elif report_type == "gender":
        add_analysis_sheet(
            workbook, "Gender Summary", "gender", employees
        )

        add_analysis_sheet(
            workbook, "Gender by Station", "station", employees
        )

        add_analysis_sheet(
            workbook, "Designations", "designation", employees
        )

    elif report_type == "data_quality":
        sheet = workbook.create_sheet("Data Quality")

        sheet.append([
            "Employee Information",
            "Missing Records",
            "Completeness",
        ])

        total = data["total"]

        fields = [
            ("Employee number", "employee_number"),
            ("Gender", "gender"),
            ("Designation", "designation"),
            ("Job group", "job_group"),
            ("Appointment type", "appointment_type"),
            ("Arrival date", "date_of_arrival"),
            ("Station", "station"),
            ("Phone number", "phone_number"),
            ("Ethnicity", "ethnicity"),
            ("Status", "status"),
        ]

        for label, field in fields:
            missing = count_missing_values(employees, field)

            completeness = (
                (total - missing) / total
                if total else 0
            )

            sheet.append([
                label,
                missing,
                completeness,
            ])

        for row in range(2, sheet.max_row + 1):
            sheet.cell(row, 3).number_format = "0.00%"

        style_excel_sheet(
            sheet,
            {"A": 30, "B": 20, "C": 20},
        )

    # Format the summary sheet
    summary.column_dimensions["A"].width = 32
    summary.column_dimensions["B"].width = 35

    return workbook


# ------------------------------------------------------
# EXCEL EXPORT
# ------------------------------------------------------

@login_required
def export_excel(request):
    data = get_report_data(request)

    workbook = build_excel_report(data)

    response = HttpResponse(
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
    )

    filename = (
        f"{data['report_type']}_"
        f"{timezone.localdate().strftime('%Y%m%d')}.xlsx"
    )

    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )

    workbook.save(response)

    return response


# ------------------------------------------------------
# PDF EXPORT
# ------------------------------------------------------

@login_required
def export_pdf(request):
    """
    Generate a formatted PDF report using the same filters.
    """

    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle,
            PageBreak,
        )
    except ImportError:
        return HttpResponse(
            "PDF generation requires ReportLab. "
            "Install it using: pip install reportlab",
            status=500,
        )

    data = get_report_data(request)

    employees = data["employees"]
    report_type = data["report_type"]

    buffer = BytesIO()

    page_size = landscape(A4) if report_type in (
        "employee_register", "new_employees"
    ) else A4

    document = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=data["report_title"],
        author="Workforce Insights",
    )

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="BrandTitle",
        parent=styles["Title"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#145A40"),
        alignment=TA_CENTER,
        spaceAfter=5,
    ))

    styles.add(ParagraphStyle(
        name="ReportSubtitle",
        parent=styles["Normal"],
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#52645a"),
        alignment=TA_CENTER,
        spaceAfter=15,
    ))

    styles.add(ParagraphStyle(
        name="SectionHeading",
        parent=styles["Heading2"],
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#145A40"),
        spaceBefore=12,
        spaceAfter=7,
    ))

    styles.add(ParagraphStyle(
        name="SmallCell",
        parent=styles["Normal"],
        fontSize=7,
        leading=9,
    ))

    story = []

    story.append(Paragraph(
        "WORKFORCE INSIGHTS",
        styles["BrandTitle"],
    ))

    story.append(Paragraph(
        data["report_title"],
        styles["ReportSubtitle"],
    ))

    story.append(Paragraph(
        f"Generated: {data['generated_at'].strftime('%d %B %Y, %H:%M')}",
        styles["Normal"],
    ))

    story.append(Paragraph(
        f"Total matching employees: <b>{data['total']}</b>",
        styles["Normal"],
    ))

    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "APPLIED FILTERS",
        styles["SectionHeading"],
    ))

    filter_table = Table([
        ["Filter", "Selection"],
        ["Employee state", data["filters"]["employee_state"].title()],
        ["Station", data["filters"]["station"] or "All stations"],
        ["Appointment", data["filters"]["appointment_type"] or "All appointments"],
        ["Job group", data["filters"]["job_group"] or "All job groups"],
        ["Status", data["filters"]["status"] or "All statuses"],
    ], colWidths=[45 * mm, 110 * mm])

    filter_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#145A40")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#DDE5E0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white,
            colors.HexColor("#F4F8F5"),
        ]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    story.append(filter_table)

    if report_type == "new_employees":
        story.append(Paragraph(
            f"Arrival year: <b>{data['arrival_year']}</b>",
            styles["Normal"],
        ))

    # Employee register reports
    if report_type in ("employee_register", "new_employees"):
        story.append(Paragraph(
            "EMPLOYEE REGISTER",
            styles["SectionHeading"],
        ))

        headers = [column[0] for column in EMPLOYEE_COLUMNS]

        table_data = [headers]

        for employee in employees.iterator():
            row = []

            for _, field in EMPLOYEE_COLUMNS:
                value = getattr(employee, field, None)

                if hasattr(value, "strftime"):
                    value = value.strftime("%d %b %Y")

                row.append(str(value or "—"))

            table_data.append([
                Paragraph(escape(str(value)), styles["SmallCell"])
                for value in row
            ])

        # Total width: 263 mm; fits landscape A4 with 12 mm side margins.
        widths = [
            11 * mm, 17 * mm, 34 * mm, 13 * mm,
            30 * mm, 16 * mm, 23 * mm, 21 * mm,
            19 * mm, 22 * mm, 21 * mm, 19 * mm,
            17 * mm,
        ]

        employee_table = Table(
            table_data,
            colWidths=widths,
            repeatRows=1,
        )

        employee_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#145A40")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 6.5),
            ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#DDE5E0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                colors.white,
                colors.HexColor("#F4F8F5"),
            ]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))

        story.append(employee_table)

    elif report_type in (
        "station", "appointment", "gender"
    ):
        if report_type == "station":
            fields = [
                ("Employees by station", "station"),
                ("Employees by designation", "designation"),
            ]
        elif report_type == "appointment":
            fields = [
                ("Appointment types", "appointment_type"),
                ("Job groups", "job_group"),
                ("Contract periods", "contract_period"),
            ]
        else:
            fields = [
                ("Gender distribution", "gender"),
                ("Employees by station", "station"),
                ("Employees by designation", "designation"),
            ]

        for heading, field in fields:
            story.append(Paragraph(
                heading.upper(),
                styles["SectionHeading"],
            ))

            rows = [[
                "Category",
                "Employees",
                "Percentage",
            ]]

            for item in get_aggregate(field, employees):
                count = item["total"]
                percentage = (
                    count / data["total"] * 100
                    if data["total"] else 0
                )

                rows.append([
                    str(item[field] or "Not stated"),
                    str(count),
                    f"{percentage:.2f}%",
                ])

            table = Table(
                rows,
                colWidths=[100 * mm, 35 * mm, 35 * mm],
                repeatRows=1,
            )

            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#145A40")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#DDE5E0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                    colors.white,
                    colors.HexColor("#F4F8F5"),
                ]),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]))

            story.append(table)
            story.append(Spacer(1, 8))

    elif report_type == "data_quality":
        story.append(Paragraph(
            "DATA COMPLETENESS",
            styles["SectionHeading"],
        ))

        fields = [
            ("Employee number", "employee_number"),
            ("Gender", "gender"),
            ("Designation", "designation"),
            ("Job group", "job_group"),
            ("Appointment type", "appointment_type"),
            ("Arrival date", "date_of_arrival"),
            ("Station", "station"),
            ("Phone number", "phone_number"),
            ("Ethnicity", "ethnicity"),
            ("Status", "status"),
        ]

        rows = [[
            "Employee information",
            "Missing records",
            "Complete records",
            "Completeness",
        ]]

        for label, field in fields:
            missing = count_missing_values(employees, field)

            complete = data["total"] - missing

            percentage = (
                complete / data["total"] * 100
                if data["total"] else 0
            )

            rows.append([
                label,
                str(missing),
                str(complete),
                f"{percentage:.2f}%",
            ])

        table = Table(
            rows,
            colWidths=[65 * mm, 35 * mm, 35 * mm, 35 * mm],
            repeatRows=1,
        )

        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#145A40")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#DDE5E0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                colors.white,
                colors.HexColor("#F4F8F5"),
            ]),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))

        story.append(table)

    def add_page_number(canvas, doc):
        canvas.saveState()

        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#718096"))

        canvas.drawString(
            12 * mm,
            8 * mm,
            "Workforce Insights | Confidential Management Report",
        )

        canvas.drawRightString(
            doc.pagesize[0] - 12 * mm,
            8 * mm,
            f"Page {doc.page}",
        )

        canvas.restoreState()

    document.build(
        story,
        onFirstPage=add_page_number,
        onLaterPages=add_page_number,
    )

    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/pdf",
    )

    filename = (
        f"{report_type}_"
        f"{timezone.localdate().strftime('%Y%m%d')}.pdf"
    )

    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )

    return response
