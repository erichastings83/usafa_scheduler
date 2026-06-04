# USAFA Teaching Schedule Generator

This Dash app generates Outlook-compatible `.ics` and `.csv` files for USAFA teaching schedules.

## Recent Updates

- **Preview Enhancements**: 
  - Events in the preview table are now sorted strictly chronologically by Date.
  - The "Type" column is color-coded for quick visual distinction between Teaching and Academic events.
- **Improved UI and Validation**:
  - Required fields (`*`) and `(Optional)` fields are now clearly marked in the Add Courses section.
  - Missing required fields are instantly highlighted with a red border upon clicking preview/download.
  - The "Periods" dropdown is expanded to show more options at once.
  - Added contact information directly into the footer.
- **Export Options**: 
  - Added a new export mode to generate "Other relevant events only".
  - Academic calendar events are now forced to show as "Free" in Outlook, preventing calendar block-outs. 
  - Clarified that reminders for academic events are always disabled.
- **Calendar Support**:
  - Bundles the Fall 2026 academic calendar as the default option.
  - Users can easily drag-and-drop a new USAFA Academic Calendar CSV to override the bundled default for their session.

## Repository structure

```text
app.py
logic.py
requirements.txt
Procfile
render.yaml
README.md
data/
  Fall 26 - Academic Calendar.csv
assets/
```

## Local run

```bash
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:8050/`.

## Render deployment

Create a Render web service connected to the GitHub repository. The included `render.yaml` uses:

```text
pip install -r requirements.txt
gunicorn app:server --bind 0.0.0.0:$PORT
```
