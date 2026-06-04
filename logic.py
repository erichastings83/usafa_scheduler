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

APP_DIR = Path(__file__).resolve().parent
DEFAULT_CALENDAR_FILENAME = "Fall 26 - Academic Calendar.csv"
DEFAULT_CALENDAR_PATH = APP_DIR / "data" / DEFAULT_CALENDAR_FILENAME

def get_bundled_calendar_date() -> str:
    if DEFAULT_CALENDAR_PATH.exists():
        mtime = DEFAULT_CALENDAR_PATH.stat().st_mtime
        return datetime.fromtimestamp(mtime).strftime("%B %d, %Y")
    return "Unknown date"

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
    return datetime.combine(date(2000, 1, 1), t).strftime("%I:%M:%S %p").lstrip("0")


def parse_time(value: Any, default: time = time(0, 0)) -> time:
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
    if not contents:
        if not DEFAULT_CALENDAR_PATH.exists():
            raise ValueError(
                f"The bundled default calendar was not found at {DEFAULT_CALENDAR_PATH}. "
                "Upload a USAFA Academic Calendar CSV to continue."
            )
        try:
            df = pd.read_csv(DEFAULT_CALENDAR_PATH, encoding="utf-8-sig")
        except Exception as exc:
            raise ValueError("The bundled default academic calendar could not be read as a CSV.") from exc
    else:
        try:
            _, encoded = contents.split(",", 1)
            decoded = base64.b64decode(encoded)
            df = pd.read_csv(io.BytesIO(decoded), encoding="utf-8-sig")
        except Exception as exc:
            raise ValueError("The uploaded replacement file could not be read as a CSV.") from exc
            
    # Clean up column names to remove any accidental literal BOM characters
    df.columns = [str(c).replace('ï»¿', '').replace('\ufeff', '').strip() for c in df.columns]
    
    return df


def extract_schedule_days(calendar_df: pd.DataFrame):
    required = {"Subject", "Start Date"}
    missing = required - set(calendar_df.columns)
    if missing:
        raise ValueError(f"Calendar CSV is missing required columns: {', '.join(sorted(missing))}")

    schedule_days = []
    modified_dates = set()
    all_dates = []

    for _, row in calendar_df.iterrows():
        subject = str(row.get("Subject", "")).replace('ï»¿', '').replace('\ufeff', '').strip()
        try:
            start_date = parse_date(row.get("Start Date", ""))
            all_dates.append(start_date)
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
    
    full_range = (min(all_dates), max(all_dates)) if all_dates else None
    return schedule_days, modified_dates, full_range


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
    schedule_days, modified_dates, _ = extract_schedule_days(calendar_df)
    events = []

    for course in course_rows:
        selected = set(course["periods"])
        invalid = [p for p in selected if not re.fullmatch(r"[MT][1-6]", p)]
        if invalid:
            raise ValueError(f"Invalid period(s): {', '.join(invalid)}")

        categories = course["categories"]


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
                    "categories": categories,
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
    if academic_mode == "none":
        return calendar_df.iloc[0:0].copy()
    if academic_mode in ("all", "academic"):
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
    res = {header: clean_value(row.get(header, "")) for header in OUTLOOK_HEADERS}
    res["Show time as"] = "0"
    return res


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
    escaped_cats = ",".join(escape_ics(c.strip()) for c in str(categories).split(",") if c.strip())
    lines.extend([
        f"SUMMARY:{escape_ics(subject)}",
        f"LOCATION:{escape_ics(location)}",
        f"DESCRIPTION:{escape_ics(description)}",
        f"CATEGORIES:{escaped_cats}",
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
    subject = clean_value(row.get("Subject", "")).replace('ï»¿', '').replace('\ufeff', '').strip()
    if not subject:
        return
    start_date = parse_date(row.get("Start Date", ""))
    end_date = parse_date(row.get("End Date", row.get("Start Date", "")))
    is_all_day = truthy(row.get("All day event", False))
    location = clean_value(row.get("Location", ""))
    description = clean_value(row.get("Description", ""))
    categories = clean_value(row.get("Categories", ""))
    show_time_as = "0"
    private = truthy(row.get("Private", False))
    uid_src = f"academic|{subject}|{start_date}|{clean_value(row.get('Start Time', ''))}|{location}"
    uid = hashlib.sha1(uid_src.encode()).hexdigest() + "@usafa-scheduler"
    lines.extend(["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{now}"])
    if is_all_day:
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
