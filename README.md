# USAFA Scheduler — Render deployment bundle (v6)

This Dash app creates Outlook-ready teaching calendars. It now bundles the Fall 2026 USAFA Academic Calendar as the default input. Users can immediately select their courses and periods without uploading a file. They can still upload another USAFA Academic Calendar CSV to replace the bundled calendar for that session.

## Repository contents

```text
app.py
requirements.txt
Procfile
render.yaml
data/
  Fall 26 - Academic Calendar.csv
```

## Deploy on Render

Upload all of these files and folders to the root of a GitHub repository. Create a Render Web Service with:

```text
Build command: pip install -r requirements.txt
Start command: gunicorn app:server --bind 0.0.0.0:$PORT
```

The included `render.yaml` contains the same service configuration.

## Default calendar behavior

- When no file is uploaded, the app reads `data/Fall 26 - Academic Calendar.csv`.
- When a user uploads another CSV, that replacement file is used for preview and download during the current browser session.
- The uploaded replacement does not modify the bundled CSV on the server.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:8050/`.
