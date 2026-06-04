# USAFA Teaching Schedule Generator — Render Deployment Bundle v7

This Dash app generates Outlook-compatible `.ics` and `.csv` files for USAFA teaching schedules.

## v7 updates

- Added a preview-size dropdown with 10, 20, 50, 100, or all appointments.
- The preview limit changes only the on-screen table; it does not remove appointments from downloads.
- Bundles the Fall 2026 academic calendar as the default option.
- Users can upload another USAFA Academic Calendar CSV to override the bundled default for their session.
- Corrected the bundled CSV filename so the fallback file works after a fresh deployment.

## Repository structure

```text
app.py
requirements.txt
Procfile
render.yaml
README.md
data/
  Fall 26 - Academic Calendar.csv
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
