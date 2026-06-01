from __future__ import annotations

import os
import base64
import csv
import hashlib
import io
import re
from pathlib import Path
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

import pandas as pd
from dash import ALL, Dash, Input, Output, State, ctx, dash_table, dcc, html

APP_DIR = Path(__file__).resolve().parent
DEFAULT_CALENDAR_FILENAME = "Fall 26 - Academic Calendar.csv"
DEFAULT_CALENDAR_PATH = APP_DIR / "data" / DEFAULT_CALENDAR_FILENAME

NORMAL_PERIOD_TIMES = {
    "1": (time(7, 30), time(8, 23)),
    "2": (time(8, 30), time(9, 23)),
    "3": (time(9, 30), time(10, 23)),
    "4": (time(10, 30), time(11, 23)),
    "5": (time(13, 30), time(14, 23)),
    "6": (time(14, 30), time(15, 23)),
}

MODIFIED_SOC_PERIOD_TIMES = {
    "1": NORMAL_PERIOD_TIMES["1"],
    "2": NORMAL_PERIOD_TIMES["2"],
    "3": NORMAL_PERIOD_TIMES["3"],
    "4": NORMAL_PERIOD_TIMES["4"],
    "5": (time(12, 30), time(13, 23)),
    "6": (time(13, 30), time(14, 23)),
}

PERIOD_OPTIONS = [
    {"label": p, "value": p}
    for p in [f"M{i}" for i in range(1, 7)] + [f"T{i}" for i in range(1, 7)]
]

OUTLOOK_HEADERS = [
    "Subject", "Start Date", "Start Time", "End Date", "End Time", "All day event",
    "Reminder on/off", "Reminder Date", "Reminder Time", "Meeting Organizer",
    "Required Attendees", "Optional Attendees", "Meeting Resources", "Billing Information",
    "Categories", "Description", "Location", "Mileage", "Priority", "Private",
    "Sensitivity", "Show time as"
]

DATE_PATTERNS = ["%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"]


def parse_date(value: Any) -> date:
    value = str(value).strip()
    for fmt in DATE_PATTERNS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value).date()
    except ValueError as exc:
        raise ValueError(f"Could not parse date: {value!r}") from exc


def fmt_date(d: date) -> str:
    return f"{d.month}/{d.day}/{d.year}"


def fmt_time(t: time) -> str:
    # Portable formatting for Windows and macOS/Linux.
    return datetime.combine(date(2000, 1, 1), t).strftime("%I:%M:%S %p").lstrip("0")


def parse_time(value: Any, default: time = time(0, 0)) -> time:
    """Parse common Outlook CSV time formats."""
    if value is None or pd.isna(value) or str(value).strip() == "":
        return default
    text = str(value).strip()
    for fmt in ("%I:%M:%S %p", "%I:%M %p", "%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Could not parse time: {text!r}")


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or pd.isna(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def clean_value(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value)


def ics_utc_dt(d: date, t: time, timezone_name: str = "America/Denver") -> str:
    """Convert a USAFA-local class time to an unambiguous UTC ICS timestamp."""
    local_dt = datetime.combine(d, t).replace(tzinfo=ZoneInfo(timezone_name))
    return local_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def escape_ics(text: str) -> str:
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def parse_uploaded_csv(contents: str | None = None) -> pd.DataFrame:
    """Read an uploaded replacement CSV, or fall back to the bundled USAFA calendar."""
    if not contents:
        if not DEFAULT_CALENDAR_PATH.exists():
            raise ValueError(
                f"The bundled default calendar was not found at {DEFAULT_CALENDAR_PATH}. "
                "Upload a USAFA Academic Calendar CSV to continue."
            )
        try:
            return pd.read_csv(DEFAULT_CALENDAR_PATH, encoding="utf-8-sig")
        except Exception as exc:
            raise ValueError("The bundled default academic calendar could not be read as a CSV.") from exc
    try:
        _, encoded = contents.split(",", 1)
        decoded = base64.b64decode(encoded)
        return pd.read_csv(io.BytesIO(decoded), encoding="utf-8-sig")
    except Exception as exc:
        raise ValueError("The uploaded replacement file could not be read as a CSV.") from exc


def extract_schedule_days(calendar_df: pd.DataFrame):
    required = {"Subject", "Start Date"}
    missing = required - set(calendar_df.columns)
    if missing:
        raise ValueError(f"Calendar CSV is missing required columns: {', '.join(sorted(missing))}")

    schedule_days = []
    modified_dates = set()

    for _, row in calendar_df.iterrows():
        subject = str(row.get("Subject", "")).strip()
        try:
            start_date = parse_date(row.get("Start Date", ""))
        except Exception:
            continue

        if "Modified SOC" in subject and "Afternoon Sections Start 1 Hour Early" in subject:
            modified_dates.add(start_date)

        match = re.fullmatch(r"([MT])(\d+)", subject)
        if match:
            schedule_days.append((start_date, match.group(1), int(match.group(2))))

    schedule_days.sort(key=lambda x: (x[0], x[1], x[2]))
    if not schedule_days:
        raise ValueError("No M-Day/T-Day rows were found. Expected subjects such as M1, M2, T1, or T2.")
    return schedule_days, modified_dates


def assemble_course_rows(names, periods, locations, descriptions, categories, allow_empty=False):
    rows = []
    for name, selected_periods, location, description, category in zip(
        names or [], periods or [], locations or [], descriptions or [], categories or []
    ):
        course_name = str(name or "").strip()
        selected_periods = selected_periods or []
        if course_name and selected_periods:
            rows.append({
                "course": course_name,
                "periods": [str(p).upper() for p in selected_periods],
                "location": str(location or "").strip(),
                "description": str(description or "").strip(),
                "categories": str(category or "Teaching").strip() or "Teaching",
            })
    if not rows and not allow_empty:
        raise ValueError("Add at least one course with a course name and one or more selected periods.")
    return rows


def build_events(calendar_df, course_rows, reminder_on, reminder_minutes, busy_status, private):
    schedule_days, modified_dates = extract_schedule_days(calendar_df)
    events = []

    for course in course_rows:
        selected = set(course["periods"])
        invalid = [p for p in selected if not re.fullmatch(r"[MT][1-6]", p)]
        if invalid:
            raise ValueError(f"Invalid period(s): {', '.join(invalid)}")

        for d, day_type, _day_number in schedule_days:
            for period in sorted(selected):
                if period[0] != day_type:
                    continue
                times = MODIFIED_SOC_PERIOD_TIMES if d in modified_dates else NORMAL_PERIOD_TIMES
                start_t, end_t = times[period[1]]
                desc_parts = [course["description"]] if course["description"] else []
                if d in modified_dates:
                    desc_parts.append("Modified SOC: afternoon sections start one hour early.")
                reminder_dt = datetime.combine(d, start_t) - timedelta(minutes=int(reminder_minutes or 0))
                events.append({
                    "period": period,
                    "date": d,
                    "start": start_t,
                    "end": end_t,
                    "subject": f"{course['course']} {period}",
                    "location": course["location"],
                    "description": "\n".join(desc_parts),
                    "categories": course["categories"],
                    "modified_soc": d in modified_dates,
                    "reminder_on": reminder_on,
                    "reminder_minutes": int(reminder_minutes or 0),
                    "reminder_date": reminder_dt.date(),
                    "reminder_time": reminder_dt.time(),
                    "show_time_as": busy_status,
                    "private": private,
                })

    events.sort(key=lambda e: (e["date"], e["start"], e["subject"]))
    return events


def filter_academic_rows(calendar_df: pd.DataFrame, academic_mode: str):
    """Return academic-calendar rows selected for export.

    academic_mode values:
      - none: no uploaded academic calendar events
      - all: every row in the uploaded CSV
    """
    if academic_mode == "none":
        return calendar_df.iloc[0:0].copy()
    if academic_mode == "all":
        return calendar_df.copy()
    raise ValueError(f"Unknown academic calendar export mode: {academic_mode!r}")


def teaching_event_to_csv_row(e):
    return {
        "Subject": e["subject"],
        "Start Date": fmt_date(e["date"]),
        "Start Time": fmt_time(e["start"]),
        "End Date": fmt_date(e["date"]),
        "End Time": fmt_time(e["end"]),
        "All day event": "False",
        "Reminder on/off": "True" if e["reminder_on"] else "False",
        "Reminder Date": fmt_date(e["reminder_date"]) if e["reminder_on"] else "",
        "Reminder Time": fmt_time(e["reminder_time"]) if e["reminder_on"] else "",
        "Meeting Organizer": "",
        "Required Attendees": "",
        "Optional Attendees": "",
        "Meeting Resources": "",
        "Billing Information": "",
        "Categories": e["categories"],
        "Description": e["description"],
        "Location": e["location"],
        "Mileage": "",
        "Priority": "Normal",
        "Private": "True" if e["private"] else "False",
        "Sensitivity": "Private" if e["private"] else "Normal",
        "Show time as": e["show_time_as"],
    }


def academic_row_to_csv_row(row):
    return {header: clean_value(row.get(header, "")) for header in OUTLOOK_HEADERS}


def events_to_outlook_csv(events, calendar_df=None, academic_mode="none"):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=OUTLOOK_HEADERS)
    writer.writeheader()
    for e in events:
        writer.writerow(teaching_event_to_csv_row(e))
    if calendar_df is not None:
        for _, row in filter_academic_rows(calendar_df, academic_mode).iterrows():
            writer.writerow(academic_row_to_csv_row(row))
    return out.getvalue()


def add_common_ics_lines(lines, subject, location, description, categories, show_time_as, private):
    lines.extend([
        f"SUMMARY:{escape_ics(subject)}",
        f"LOCATION:{escape_ics(location)}",
        f"DESCRIPTION:{escape_ics(description)}",
        f"CATEGORIES:{escape_ics(categories)}",
        "TRANSP:TRANSPARENT" if str(show_time_as) == "0" else "TRANSP:OPAQUE",
        "CLASS:PRIVATE" if private else "CLASS:PUBLIC",
    ])


def add_ics_alarm(lines, minutes_before, subject):
    lines.extend([
        "BEGIN:VALARM",
        f"TRIGGER:-PT{int(minutes_before)}M",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{escape_ics(subject)}",
        "END:VALARM",
    ])


def academic_row_to_ics(lines, row, now, timezone_name):
    subject = clean_value(row.get("Subject", "")).strip()
    if not subject:
        return
    start_date = parse_date(row.get("Start Date", ""))
    end_date = parse_date(row.get("End Date", row.get("Start Date", "")))
    is_all_day = truthy(row.get("All day event", False))
    location = clean_value(row.get("Location", ""))
    description = clean_value(row.get("Description", ""))
    categories = clean_value(row.get("Categories", ""))
    show_time_as = clean_value(row.get("Show time as", "2")) or "2"
    private = truthy(row.get("Private", False))
    uid_src = f"academic|{subject}|{start_date}|{clean_value(row.get('Start Time', ''))}|{location}"
    uid = hashlib.sha1(uid_src.encode()).hexdigest() + "@usafa-scheduler"
    lines.extend(["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{now}"])
    if is_all_day:
        # For all-day events, DTEND is exclusive. The Outlook CSV already uses
        # the following day, so preserve it directly.
        lines.extend([
            f"DTSTART;VALUE=DATE:{start_date.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{end_date.strftime('%Y%m%d')}",
        ])
    else:
        start_t = parse_time(row.get("Start Time", ""))
        end_t = parse_time(row.get("End Time", ""))
        lines.extend([
            f"DTSTART:{ics_utc_dt(start_date, start_t, timezone_name)}",
            f"DTEND:{ics_utc_dt(end_date, end_t, timezone_name)}",
        ])
    add_common_ics_lines(lines, subject, location, description, categories, show_time_as, private)
    # The uploaded USAFA file controls whether its own events have reminders.
    # When present, calculate the alarm offset from the uploaded reminder fields.
    if truthy(row.get("Reminder on/off", False)) and not is_all_day:
        try:
            reminder_date = parse_date(row.get("Reminder Date", ""))
            reminder_time = parse_time(row.get("Reminder Time", ""))
            start_dt = datetime.combine(start_date, parse_time(row.get("Start Time", "")))
            reminder_dt = datetime.combine(reminder_date, reminder_time)
            minutes_before = max(0, int((start_dt - reminder_dt).total_seconds() // 60))
            add_ics_alarm(lines, minutes_before, subject)
        except Exception:
            pass
    lines.append("END:VEVENT")


def events_to_ics(events, calendar_df=None, academic_mode="none", timezone_name="America/Denver"):
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//USAFA Scheduler//Teaching Schedule App//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
    ]
    for e in events:
        uid_src = f"teaching|{e['subject']}|{e['date']}|{e['start']}|{e['location']}"
        uid = hashlib.sha1(uid_src.encode()).hexdigest() + "@usafa-scheduler"
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now}",
            f"DTSTART:{ics_utc_dt(e['date'], e['start'], timezone_name)}",
            f"DTEND:{ics_utc_dt(e['date'], e['end'], timezone_name)}",
        ])
        add_common_ics_lines(lines, e["subject"], e["location"], e["description"], e["categories"], e["show_time_as"], e["private"])
        if e["reminder_on"]:
            add_ics_alarm(lines, e["reminder_minutes"], e["subject"])
        lines.append("END:VEVENT")
    if calendar_df is not None:
        for _, row in filter_academic_rows(calendar_df, academic_mode).iterrows():
            academic_row_to_ics(lines, row, now, timezone_name)
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

# USAFA-inspired blue and silver theme.
COLORS = {
    "navy": "#003B70",
    "blue": "#0076A8",
    "sky": "#DCEFF7",
    "silver": "#A7A9AC",
    "silver_light": "#F2F4F5",
    "ink": "#16324F",
    "white": "#FFFFFF",
    "success": "#0F6B4F",
}

PAGE_STYLE = {
    "fontFamily": "Arial, Helvetica, sans-serif",
    "backgroundColor": COLORS["silver_light"],
    "minHeight": "100vh",
    "color": COLORS["ink"],
}

CONTENT_STYLE = {
    "maxWidth": "1180px",
    "margin": "0 auto",
    "padding": "24px",
}

CARD_STYLE = {
    "backgroundColor": COLORS["white"],
    "border": f"1px solid {COLORS['silver']}",
    "borderRadius": "10px",
    "boxShadow": "0 2px 6px rgba(0, 59, 112, 0.10)",
    "padding": "18px",
    "marginBottom": "16px",
}

BUTTON_STYLE = {
    "backgroundColor": COLORS["navy"],
    "color": COLORS["white"],
    "border": "none",
    "borderRadius": "5px",
    "padding": "10px 15px",
    "fontWeight": "bold",
    "cursor": "pointer",
}

SECONDARY_BUTTON_STYLE = {
    **BUTTON_STYLE,
    "backgroundColor": COLORS["blue"],
}


def field(label, component, width="220px"):
    return html.Div(
        [html.Label(label, style={"fontWeight": "bold", "color": COLORS["navy"], "display": "block", "marginBottom": "5px"}), component],
        style={"display": "inline-block", "verticalAlign": "top", "marginRight": "12px", "marginBottom": "10px", "width": width},
    )


def make_course_row(index):
    return html.Div([
        html.H5(f"Course {index + 1}", style={"margin": "0 0 10px 0", "color": COLORS["navy"]}),
        field("Course name", dcc.Input(id={"type": "course-name", "index": index}, type="text", placeholder="e.g., Math 356", style={"width": "100%", "padding": "7px"})),
        field("Periods", dcc.Dropdown(id={"type": "course-periods", "index": index}, options=PERIOD_OPTIONS, multi=True, placeholder="Select M/T periods"), width="290px"),
        field("Location", dcc.Input(id={"type": "course-location", "index": index}, type="text", placeholder="e.g., Fairchild Hall 2E17", style={"width": "100%", "padding": "7px"})),
        html.Br(),
        field("Description", dcc.Input(id={"type": "course-description", "index": index}, type="text", placeholder="Optional", style={"width": "100%", "padding": "7px"}), width="520px"),
        field("Category", dcc.Input(id={"type": "course-category", "index": index}, type="text", value="Teaching", style={"width": "100%", "padding": "7px"}), width="180px"),
    ], style={
        "border": f"1px solid {COLORS['silver']}",
        "borderLeft": f"5px solid {COLORS['blue']}",
        "borderRadius": "7px",
        "padding": "14px",
        "marginBottom": "12px",
        "backgroundColor": COLORS["silver_light"],
    })


app = Dash(__name__, suppress_callback_exceptions=True)
server = app.server
app.title = "USAFA Teaching Schedule Generator"

app.layout = html.Div([
    html.Div([
        html.Div([
            html.Div("UNITED STATES AIR FORCE ACADEMY", style={"fontSize": "13px", "letterSpacing": "1.5px", "fontWeight": "bold", "color": COLORS["sky"]}),
            html.H1("Teaching Schedule Generator", style={"margin": "5px 0 2px 0", "fontSize": "31px", "color": COLORS["white"]}),
            html.Div("Create Outlook-ready calendars using the bundled USAFA academic calendar or an uploaded replacement CSV.", style={"color": COLORS["white"], "fontSize": "15px"}),
        ], style={"maxWidth": "1180px", "margin": "0 auto", "padding": "20px 24px"}),
    ], style={"backgroundColor": COLORS["navy"], "borderBottom": f"6px solid {COLORS['blue']}"}),

    html.Div([
        html.Div([
            html.H3("1. Academic calendar", style={"color": COLORS["navy"], "marginTop": "0"}),
            html.P("The Fall 2026 USAFA Academic Calendar is loaded by default. Upload another CSV only when you want to replace it.", style={"marginTop": "0", "color": COLORS["ink"]}),
            dcc.Upload(
                id="calendar-upload",
                children=html.Div([html.Strong("Optional: drag and drop"), " or select a replacement Academic Calendar CSV"]),
                style={
                    "border": f"2px dashed {COLORS['blue']}",
                    "borderRadius": "7px",
                    "padding": "22px",
                    "maxWidth": "720px",
                    "textAlign": "center",
                    "backgroundColor": COLORS["sky"],
                    "color": COLORS["navy"],
                    "cursor": "pointer",
                },
                multiple=False,
            ),
            html.Div(id="upload-status", style={"margin": "12px 0 0 0", "fontWeight": "bold", "color": COLORS["success"]}),
        ], style=CARD_STYLE),

        html.Div([
            html.H3("2. Add courses", style={"color": COLORS["navy"], "marginTop": "0"}),
            html.Div(id="course-rows", children=[make_course_row(0)]),
            html.Button("Add course row", id="add-row", n_clicks=0, style=SECONDARY_BUTTON_STYLE),
        ], style=CARD_STYLE),

        html.Div([
            html.H3("3. Choose calendar options", style={"color": COLORS["navy"], "marginTop": "0"}),
            html.Label("Include uploaded USAFA Academic Calendar events in the export", style={"fontWeight": "bold", "color": COLORS["navy"]}),
            dcc.RadioItems(
                id="academic-export-mode",
                options=[
                    {"label": " Teaching appointments only", "value": "none"},
                    {"label": " Teaching appointments + every uploaded USAFA Academic Calendar event", "value": "all"},
                ],
                value="none",
                style={"margin": "8px 0 16px 0"},
                labelStyle={"display": "block", "marginBottom": "6px"},
            ),
            html.Label("Reminder for teaching appointments", style={"fontWeight": "bold", "color": COLORS["navy"]}),
            dcc.RadioItems(
                id="reminder-on",
                options=[{"label": " No reminder", "value": "no"}, {"label": " Reminder", "value": "yes"}],
                value="yes",
                inline=True,
                style={"margin": "7px 0 10px 0"},
                labelStyle={"marginRight": "18px"},
            ),
            html.Label("Reminder minutes before class", style={"fontWeight": "bold", "color": COLORS["navy"], "display": "block"}),
            dcc.Input(id="reminder-minutes", type="number", value=15, min=0, step=5, style={"padding": "7px", "width": "110px", "margin": "6px 0 14px 0"}),
            html.Label("Show time as", style={"fontWeight": "bold", "color": COLORS["navy"], "display": "block"}),
            dcc.Dropdown(id="busy-status", options=[{"label": "Free", "value": "0"}, {"label": "Tentative", "value": "1"}, {"label": "Busy", "value": "2"}, {"label": "Out of Office", "value": "3"}], value="2", style={"width": "240px", "margin": "6px 0 12px 0"}),
            dcc.Checklist(id="private", options=[{"label": " Mark appointments private", "value": "private"}], value=[]),
        ], style=CARD_STYLE),

        html.Div([
            html.H3("4. Preview or download", style={"color": COLORS["navy"], "marginTop": "0"}),
            html.Button("Preview events", id="preview", n_clicks=0, style=SECONDARY_BUTTON_STYLE),
            html.Button("Download .ics", id="download-ics", n_clicks=0, style={**BUTTON_STYLE, "marginLeft": "10px"}),
            html.Button("Download Outlook .csv", id="download-csv", n_clicks=0, style={**BUTTON_STYLE, "marginLeft": "10px"}),
            dcc.Download(id="download"),
            html.Div(id="message", style={"marginTop": "16px", "fontWeight": "bold", "color": COLORS["navy"]}),
            html.Div(id="preview-table", style={"marginTop": "16px"}),
        ], style=CARD_STYLE),
    ], style=CONTENT_STYLE),
], style=PAGE_STYLE)


@app.callback(Output("course-rows", "children"), Input("add-row", "n_clicks"), State("course-rows", "children"), prevent_initial_call=True)
def add_course_row(_n_clicks, children):
    children = children or []
    children.append(make_course_row(len(children)))
    return children


@app.callback(Output("upload-status", "children"), Input("calendar-upload", "contents"), State("calendar-upload", "filename"))
def upload_status(contents, filename):
    try:
        df = parse_uploaded_csv(contents)
        days, modified = extract_schedule_days(df)
        source = filename if contents else f"bundled default: {DEFAULT_CALENDAR_FILENAME}"
        return f"Loaded {source}: found {len(days)} M/T class days and {len(modified)} modified SOC day(s)."
    except Exception as exc:
        return f"Calendar problem: {exc}"


def make_events_from_state(contents, names, periods, locations, descriptions, categories, academic_mode, reminder_value, reminder_minutes, busy_status, private_values):
    df = parse_uploaded_csv(contents)
    course_rows = assemble_course_rows(
        names, periods, locations, descriptions, categories,
        allow_empty=(academic_mode != "none"),
    )
    events = build_events(
        df,
        course_rows,
        reminder_on=(reminder_value == "yes"),
        reminder_minutes=int(reminder_minutes or 0),
        busy_status=str(busy_status or "2"),
        private=("private" in (private_values or [])),
    ) if course_rows else []
    return df, events


COURSE_STATES = [
    State({"type": "course-name", "index": ALL}, "value"),
    State({"type": "course-periods", "index": ALL}, "value"),
    State({"type": "course-location", "index": ALL}, "value"),
    State({"type": "course-description", "index": ALL}, "value"),
    State({"type": "course-category", "index": ALL}, "value"),
]


@app.callback(
    Output("message", "children"),
    Output("preview-table", "children"),
    Input("preview", "n_clicks"),
    State("calendar-upload", "contents"),
    *COURSE_STATES,
    State("academic-export-mode", "value"),
    State("reminder-on", "value"), State("reminder-minutes", "value"), State("busy-status", "value"), State("private", "value"),
    prevent_initial_call=True,
)
def preview_events(_n_clicks, contents, names, periods, locations, descriptions, categories, academic_mode, reminder_value, reminder_minutes, busy_status, private_values):
    try:
        df, events = make_events_from_state(contents, names, periods, locations, descriptions, categories, academic_mode, reminder_value, reminder_minutes, busy_status, private_values)
        academic_df = filter_academic_rows(df, academic_mode)
        sample = [
            {"Type": "Teaching", "Date": fmt_date(e["date"]), "Start": fmt_time(e["start"]), "End": fmt_time(e["end"]), "Subject": e["subject"], "Location": e["location"], "Modified SOC": "Yes" if e["modified_soc"] else ""}
            for e in events[:20]
        ]
        remaining = max(0, 20 - len(sample))
        for _, row in academic_df.head(remaining).iterrows():
            sample.append({
                "Type": "Academic calendar",
                "Date": clean_value(row.get("Start Date", "")),
                "Start": "All day" if truthy(row.get("All day event", False)) else clean_value(row.get("Start Time", "")),
                "End": clean_value(row.get("End Date", "")) if truthy(row.get("All day event", False)) else clean_value(row.get("End Time", "")),
                "Subject": clean_value(row.get("Subject", "")),
                "Location": clean_value(row.get("Location", "")),
                "Modified SOC": "",
            })
        table = dash_table.DataTable(
            data=sample,
            page_size=20,
            style_cell={"textAlign": "left", "padding": "8px", "fontFamily": "Arial, Helvetica, sans-serif"},
            style_header={"backgroundColor": COLORS["navy"], "color": COLORS["white"], "fontWeight": "bold"},
            style_data_conditional=[{"if": {"row_index": "odd"}, "backgroundColor": COLORS["silver_light"]}],
            style_table={"overflowX": "auto", "border": f"1px solid {COLORS['silver']}"},
        )
        total = len(events) + len(academic_df)
        return f"Generated {total} events: {len(events)} teaching appointment(s) and {len(academic_df)} uploaded academic calendar event(s). Showing the first 20.", table
    except Exception as exc:
        return f"Problem: {exc}", ""


@app.callback(
    Output("download", "data"),
    Input("download-ics", "n_clicks"), Input("download-csv", "n_clicks"),
    State("calendar-upload", "contents"),
    *COURSE_STATES,
    State("academic-export-mode", "value"),
    State("reminder-on", "value"), State("reminder-minutes", "value"), State("busy-status", "value"), State("private", "value"),
    prevent_initial_call=True,
)
def download_file(_n_ics, _n_csv, contents, names, periods, locations, descriptions, categories, academic_mode, reminder_value, reminder_minutes, busy_status, private_values):
    df, events = make_events_from_state(contents, names, periods, locations, descriptions, categories, academic_mode, reminder_value, reminder_minutes, busy_status, private_values)
    if ctx.triggered_id == "download-csv":
        return dict(content=events_to_outlook_csv(events, df, academic_mode), filename="usafa_schedule.csv", type="text/csv")
    return dict(content=events_to_ics(events, df, academic_mode), filename="usafa_schedule.ics", type="text/calendar")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8050")), debug=False)
