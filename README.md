This Dash app creates Outlook-compatible calendar imports from the USAFA Academic Calendar CSV.

Users can choose one of three export modes:

1. **Teaching appointments only**
2. **Teaching + major academic calendar events** — excludes the daily M/T rotation labels such as `M1`, `T1`, `M2`, and `T2`
3. **Teaching + every uploaded CSV event** — includes every row from the uploaded USAFA Academic Calendar CSV, including the M/T rotation labels

The app can also export academic-calendar events without adding any course rows when option 2 or 3 is selected.

## Existing features

- Upload a USAFA Academic Calendar CSV
- Add multiple courses
- Select any combination of M1–M6 and T1–T6 periods for each course
- Enter course names, locations, descriptions, and categories
- Add reminders to teaching appointments
- Mark teaching appointments private and set their Outlook busy status
- Automatically shift afternoon teaching periods on Modified SOC days
- Export `.ics` or Outlook `.csv`
- Export `.ics` teaching appointments as UTC timestamps so Outlook displays the correct Mountain-time class times through daylight-saving changes

## Run locally

```bash
pip install dash pandas
python usafa_scheduler_app_v4.py
```

Then open:

```text
http://127.0.0.1:8050/
```

## Recommended import workflow

Create a temporary Outlook calendar for testing before importing a large file. This makes it easy to remove an import and try a different export mode.
