
"""
Flexible spreadsheet reader for Workforce Insights.

The reader stages rows even when headings are unknown, fields are missing,
or worksheets have different layouts.

Validation and correction happen in the review workspace.
"""

import re
from datetime import date, datetime

import pandas as pd


FIELD_ALIASES = {
    "serial_number": [
        "s/no", "s/no.", "serial no", "serial number", "s no",
    ],
    "national_id_number": [
        "id/no", "id/no.", "id no", "id number", "national id",
    ],
    "employee_number": [
        "p/no", "p/no.", "pno", "payroll no", "payroll number",
        "employee number", "employee no",
    ],
    "full_name": ["name", "full name", "employee name"],
    "gender": ["gender", "sex"],
    "designation": ["designation", "job title", "position"],
    "job_group": ["j/g", "job group", "job grade"],
    "mcpsb_reference_number": [
        "mcpsb ref no", "mcpsb reference no",
        "mcpsb ref number", "mcpsb reference number",
    ],
    "county_posting_reference_number": [
        "county posting ref no", "county posting reference no",
        "county ref no", "county posting ref number",
        "county posting reference number",
    ],
    "mcpsb_letter_date": ["mcpsb letter date"],
    "appointment_type": [
        "type of appointment", "type of appoinment",
        "type of apoointment", "type of apopointment",
        "appointment type",
    ],
    "date_of_arrival": ["date of arrival"],
    "contract_period": ["contract period"],
    "station": ["station", "work station"],
    "phone_number": [
        "phone number", "phone no", "telephone", "telephone number",
    ],
    "ethnicity": ["ethnicity"],
    "area_of_deployment": ["area of deployment", "deployment area"],
    "status": ["status", "employment status"],
    "remark": ["remarks", "remark"],
}


# Confirmed 18-column layout for this headerless worksheet.
HEADERLESS_LAYOUTS = {
    "county short term nurses": [
        "S/NO",
        "ID/NO",
        "P/No.",
        "NAME",
        "GENDER",
        "DESIGNATION",
        "J/G",
        "MCPSB REF. NO",
        "COUNTY(POSTING) REF NO.",
        "MCPSB LETTER DATE",
        "TYPE OF APOPOINTMENT",
        "DATE OF ARRIVAL",
        "CONTRACT PERIOD",
        "STATION",
        "PHONE NUMBER",
        "ETHNICITY",
        "STATUS",
        "Remarks",
    ],
}


STANDARD_FIELDS = list(FIELD_ALIASES)


def normalize_header(value):
    """Normalize a spreadsheet heading for matching."""

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    value = str(value).strip().lower()
    value = re.sub(r"[\r\n\t]+", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)

    return re.sub(r"\s+", " ", value).strip()


HEADER_LOOKUP = {}

for field, aliases in FIELD_ALIASES.items():
    for alias in aliases:
        HEADER_LOOKUP[normalize_header(alias)] = field


def map_header(header):
    """Return the standard field associated with a heading."""

    return HEADER_LOOKUP.get(normalize_header(header))


def clean_cell(value):
    """Convert spreadsheet values into safe, consistent strings."""

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.strftime("%Y-%m-%d")

    # Avoid turning identifiers such as 125 into 125.0.
    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    return str(value).strip()


def trim_empty_columns(frame):
    """
    Remove only trailing columns that contain no data.

    Empty columns in the middle of a worksheet are retained because
    removing them could shift the mapping of subsequent columns.
    """

    frame = frame.copy()

    while frame.shape[1]:
        last_column = frame.iloc[:, -1]

        has_data = last_column.map(
            lambda value: clean_cell(value) != ""
        ).any()

        if has_data:
            break

        frame = frame.iloc[:, :-1]

    return frame


def remove_empty_rows(frame):
    """Remove completely empty rows without changing original row indexes."""

    if frame.empty:
        return frame.copy()

    mask = frame.apply(
        lambda row: any(
            clean_cell(value) for value in row.tolist()
        ),
        axis=1,
    )

    return frame.loc[mask].copy()


def score_header_row(row):
    """Count recognizable standard headings in a possible header row."""

    found = {
        map_header(value)
        for value in row.tolist()
    }

    found.discard(None)

    return len(found), found


def detect_header_row(frame, limit=40):
    """
    Detect a likely header row within the first 40 rows.

    At least three recognizable fields are required.
    """

    best_index = None
    best_score = 0

    for index, row in frame.head(limit).iterrows():
        score, _ = score_header_row(row)

        if score > best_score:
            best_index = index
            best_score = score

    if best_score >= 3:
        return best_index, best_score

    return None, best_score


def build_mapping(headers):
    """Build source-column-position to standard-field mapping."""

    mapping = {}
    seen = set()

    for position, header in enumerate(headers):
        field = map_header(header)

        if field and field not in seen:
            mapping[position] = field
            seen.add(field)

    return mapping


def extract_source_period(sheet_name):
    """Extract YYYY-MM from a worksheet name when month and year are clear."""

    months = {
        "january": "01",
        "february": "02",
        "march": "03",
        "april": "04",
        "may": "05",
        "june": "06",
        "july": "07",
        "august": "08",
        "september": "09",
        "october": "10",
        "november": "11",
        "december": "12",
    }

    name = str(sheet_name).lower()

    year = re.search(r"\b(20\d{2})\b", name)

    if not year:
        return ""

    for month, number in months.items():
        if re.search(rf"\b{month}\b", name):
            return f"{year.group(1)}-{number}"

    return ""


def get_worksheets(uploaded_file):
    """Return available worksheet names."""

    filename = uploaded_file.name.lower()
    uploaded_file.seek(0)

    if filename.endswith(".csv"):
        return ["CSV file"]

    if filename.endswith((".xlsx", ".xls")):
        with pd.ExcelFile(uploaded_file) as workbook:
            return list(workbook.sheet_names)

    raise ValueError(
        "Unsupported file format. Upload CSV, XLSX or XLS."
    )


def _read_sheets(uploaded_file, selected_sheets):
    """Read selected worksheets without assuming a header row."""

    filename = uploaded_file.name.lower()
    uploaded_file.seek(0)

    if filename.endswith(".csv"):
        frame = pd.read_csv(
            uploaded_file,
            header=None,
            dtype=object,
            keep_default_na=False,
        )

        return {"CSV file": frame}

    if not filename.endswith((".xlsx", ".xls")):
        raise ValueError(
            "Unsupported file format. Upload CSV, XLSX or XLS."
        )

    with pd.ExcelFile(uploaded_file) as workbook:
        available = workbook.sheet_names
        selected = selected_sheets or available

        invalid = set(selected) - set(available)

        if invalid:
            raise ValueError(
                f"Unknown worksheets selected: "
                f"{', '.join(sorted(invalid))}"
            )

        return {
            name: workbook.parse(
                sheet_name=name,
                header=None,
                dtype=object,
            )
            for name in selected
        }


def _layout_for_headerless(sheet_name, frame, known_layouts):
    """
    Resolve a headerless worksheet using an explicit layout or a
    uniquely identified layout from another worksheet.

    Unknown layouts remain unmapped for manual review.
    """

    key = normalize_header(sheet_name)
    explicit = HEADERLESS_LAYOUTS.get(key)

    frame = trim_empty_columns(frame)

    if explicit:
        expected = len(explicit)
        actual = frame.shape[1]

        headers = list(explicit[:actual])

        if actual > expected:
            headers.extend(
                f"Unmapped column {i + 1}"
                for i in range(expected, actual)
            )

        elif actual < expected:
            headers.extend(
                f"Missing source column {i + 1}"
                for i in range(actual, expected)
            )

        return (
            headers,
            build_mapping(headers),
            "Explicit worksheet layout",
        )

    candidates = known_layouts.get(frame.shape[1], [])

    signatures = {}

    for item in candidates:
        signatures[tuple(item["headers"])] = item

    if len(signatures) == 1:
        layout = next(iter(signatures.values()))

        return (
            list(layout["headers"]),
            dict(layout["mapping"]),
            f"Layout matched from {layout['sheet']}",
        )

    return (
        None,
        None,
        "No reliable heading layout detected; "
        "columns preserved for manual mapping",
    )


def _prepare_sheet(sheet_name, original, known_layouts):
    """
    Prepare one worksheet.

    Explicitly configured headerless worksheets are handled before
    automatic header detection to avoid mistaking employee data for headings.
    """

    frame = trim_empty_columns(original)

    if normalize_header(sheet_name) in HEADERLESS_LAYOUTS:
        headers, mapping, method = _layout_for_headerless(
            sheet_name,
            frame,
            known_layouts,
        )

        return {
            "frame": frame,
            "headers": headers,
            "mapping": mapping,
            "header_row": None,
            "method": method,
            "has_headers": False,
        }

    header_index, score = detect_header_row(frame)

    if header_index is not None:
        raw_headers = [
            clean_cell(value)
            for value in frame.iloc[header_index].tolist()
        ]

        while raw_headers and not raw_headers[-1]:
            raw_headers.pop()

        mapping = build_mapping(raw_headers)

        data_frame = frame.iloc[
            header_index + 1:,
            :len(raw_headers),
        ].copy()

        return {
            "frame": data_frame,
            "headers": raw_headers,
            "mapping": mapping,
            "header_row": int(header_index) + 1,
            "method": "Detected heading row",
            "has_headers": True,
        }

    return {
        "frame": frame,
        "headers": None,
        "mapping": {},
        "header_row": None,
        "method": "",
        "has_headers": False,
        "score": score,
    }


def _ensure_header_width(frame, headers):
    """Make sure the number of headings matches the worksheet columns."""

    frame = frame.copy()
    headers = list(headers)

    if frame.shape[1] > len(headers):
        headers.extend(
            f"Unmapped column {i + 1}"
            for i in range(len(headers), frame.shape[1])
        )

    elif frame.shape[1] < len(headers):
        for column in range(frame.shape[1], len(headers)):
            frame[column] = ""

    frame = frame.iloc[:, :len(headers)]
    frame.columns = headers

    return frame, headers


def _normalize_row(row, headers, mapping):
    """Convert a worksheet row into the standard staging structure."""

    normalized = {
        field: ""
        for field in STANDARD_FIELDS
    }

    extras = {}
    source_columns = {}

    for position, header in enumerate(headers):
        value = clean_cell(row.iloc[position])
        header_name = str(header)

        source_columns[header_name] = value

        field = mapping.get(position)

        if field:
            # Do not silently overwrite duplicate mapped headings.
            if not normalized[field]:
                normalized[field] = value
            else:
                extras[
                    f"{header_name} (duplicate heading)"
                ] = value
        else:
            extras[header_name] = value

    normalized["_additional_fields"] = extras
    normalized["_source_columns"] = source_columns

    return normalized


def read_workbook(uploaded_file, selected_sheets=None):
    """
    Read an uploaded workbook and return a stable staging structure.

    Unknown headings and unknown worksheets are retained for manual mapping.

    Returns:
        {
            "columns": [...],
            "records": [...],
            "total_rows": int,
            "detected_headers": {...},
            "sheet_summaries": [...]
        }
    """

    raw_sheets = _read_sheets(
        uploaded_file,
        selected_sheets,
    )

    if not raw_sheets:
        raise ValueError("No worksheets were selected.")

    # First prepare sheets with recognizable headers.
    analyzed = {}
    known_layouts = {}

    for sheet_name, original in raw_sheets.items():
        info = _prepare_sheet(
            sheet_name,
            original,
            known_layouts,
        )

        analyzed[sheet_name] = info

        if info["has_headers"]:
            known_layouts.setdefault(
                len(info["headers"]),
                [],
            ).append({
                "sheet": sheet_name,
                "headers": info["headers"],
                "mapping": info["mapping"],
            })

    records = []
    detected_headers = {}
    sheet_summaries = []

    for sheet_name, info in analyzed.items():
        frame = info["frame"]

        if not info["has_headers"] and info["headers"] is None:
            headers, mapping, method = _layout_for_headerless(
                sheet_name,
                frame,
                known_layouts,
            )

            if headers is None:
                headers = [
                    f"Unmapped column {i + 1}"
                    for i in range(frame.shape[1])
                ]

                mapping = {}

            info["headers"] = headers
            info["mapping"] = mapping
            info["method"] = method

        headers = info["headers"]
        mapping = info["mapping"]

        frame = trim_empty_columns(frame)

        frame, headers = _ensure_header_width(
            frame,
            headers,
        )

        frame = remove_empty_rows(frame)

        detected_headers[sheet_name] = (
            info["header_row"]
            if info["header_row"] is not None
            else info["method"]
        )

        sheet_count = 0

        for index, row in frame.iterrows():
            normalized = _normalize_row(
                row,
                headers,
                mapping,
            )

            # Skip only rows that are entirely empty.
            has_data = any(
                clean_cell(value)
                for key, value in normalized.items()
                if not key.startswith("_")
            )

            if not has_data:
                continue

            records.append({
                "source_sheet": sheet_name,
                "source_row_number": int(index) + 1,
                "source_period": extract_source_period(sheet_name),
                "raw_data": normalized,
                "layout_inherited": not info["has_headers"],
            })

            sheet_count += 1

        sheet_summaries.append({
            "sheet_name": sheet_name,
            "header": detected_headers[sheet_name],
            "records": sheet_count,
            "layout_inherited": not info["has_headers"],
            "columns": len(headers),
        })

    if not records:
        raise ValueError(
            "The selected worksheets contain no non-empty data rows."
        )

    all_columns = []

    for sheet_name in analyzed:
        for heading in analyzed[sheet_name]["headers"]:
            if heading not in all_columns:
                all_columns.append(heading)

    return {
        "columns": all_columns,
        "records": records,
        "total_rows": len(records),
        "detected_headers": detected_headers,
        "sheet_summaries": sheet_summaries,
    }
