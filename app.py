import os
import uuid
from dash import ALL, Dash, Input, Output, State, ctx, dash_table, dcc, html
import dash_bootstrap_components as dbc

import logic

app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)
server = app.server
app.title = "USAFA Teaching Schedule Generator"

# Custom colors to maintain USAFA branding while using Bootstrap
USAFA_NAVY = "#003B70"
USAFA_BLUE = "#0076A8"

def make_course_row():
    uid = uuid.uuid4().hex
    return dbc.Card([
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Course name", className="fw-bold"),
                    dbc.Input(id={"type": "course-name", "index": uid}, type="text", placeholder="e.g., Math 356", persistence=True, persistence_type="session"),
                ], width=12, md=3, className="mb-2 mb-md-0"),
                dbc.Col([
                    dbc.Label("Periods", className="fw-bold"),
                    dcc.Dropdown(id={"type": "course-periods", "index": uid}, options=logic.PERIOD_OPTIONS, multi=True, placeholder="Select M/T periods", persistence=True, persistence_type="session", style={"minWidth": "100%"}),
                ], width=12, md=4, className="mb-2 mb-md-0"),
                dbc.Col([
                    dbc.Label("Location", className="fw-bold"),
                    dbc.Input(id={"type": "course-location", "index": uid}, type="text", placeholder="e.g., Fairchild Hall 2E17", persistence=True, persistence_type="session"),
                ], width=12, md=3, className="mb-2 mb-md-0"),
                dbc.Col([
                    dbc.Label(html.Br(), className="d-none d-md-block"),
                    dbc.Button("🗑️ Remove", id={"type": "remove-row", "index": uid}, color="danger", outline=True, className="w-100"),
                ], width=12, md=2),
            ], className="mb-2"),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Description", className="fw-bold"),
                    dbc.Input(id={"type": "course-description", "index": uid}, type="text", placeholder="Optional", persistence=True, persistence_type="session"),
                ], width=12, md=8, className="mb-2 mb-md-0"),
                dbc.Col([
                    dbc.Label("Category", className="fw-bold"),
                    dbc.Input(id={"type": "course-category", "index": uid}, type="text", value="Teaching", persistence=True, persistence_type="session"),
                ], width=12, md=4),
            ])
        ])
    ], className="mb-3 border-start border-primary border-4", id={"type": "course-row-container", "index": uid})

app.layout = html.Div([
    # Navigation/Header
    html.Div([
        dbc.Container([
            html.Div("UNITED STATES AIR FORCE ACADEMY", style={"fontSize": "13px", "letterSpacing": "1.5px", "fontWeight": "bold", "color": "#DCEFF7"}),
            html.H1("Teaching Schedule Generator", className="text-white mt-1 mb-1"),
            html.Div("Create Outlook-ready calendars using the bundled USAFA academic calendar or an uploaded replacement CSV.", className="text-white opacity-75"),
        ], className="py-4")
    ], style={"backgroundColor": USAFA_NAVY, "borderBottom": f"6px solid {USAFA_BLUE}"}),

    dbc.Container([
        dbc.Row([
            dbc.Col([
                # Card 1: Academic Calendar
                dbc.Card([
                    dbc.CardHeader(html.H4("1. Academic Calendar", className="m-0", style={"color": USAFA_NAVY})),
                    dbc.CardBody([
                        dbc.Alert([
                            html.I(className="bi bi-check-circle-fill me-2"),
                            html.Strong("Fall 2026 USAFA Academic Calendar"), 
                            f" sourced from the DF Registrar (current as of {logic.get_bundled_calendar_date()}) is already loaded and ready to use."
                        ], color="success", className="mb-3 py-2"),
                        html.P("If you are scheduling for a different semester, you can upload a replacement CSV below. Otherwise, you can skip to Step 2.", className="text-muted mb-2"),
                        dcc.Upload(
                            id="calendar-upload",
                            children=html.Div([
                                html.I(className="bi bi-cloud-upload fs-4"), html.Br(), 
                                "Optional: ", html.Strong("Drag and drop"), " or select a replacement CSV"
                            ]),
                            style={
                                "border": f"2px dashed {USAFA_BLUE}",
                                "borderRadius": "7px",
                                "padding": "16px",
                                "textAlign": "center",
                                "backgroundColor": "#F8F9FA",
                                "color": USAFA_NAVY,
                                "cursor": "pointer",
                            },
                            multiple=False,
                        ),
                        html.Div(id="upload-status", className="mt-3 fw-bold text-success"),
                    ])
                ], className="mb-4 shadow-sm"),

                # Card 2: Add Courses
                dbc.Card([
                    dbc.CardHeader(html.H4("2. Add Courses", className="m-0", style={"color": USAFA_NAVY})),
                    dbc.CardBody([
                        html.Div(id="course-rows", children=[make_course_row()]),
                        dbc.Row([
                            dbc.Col([
                                dbc.Button("➕ Add Course Row", id="add-row", n_clicks=0, color="primary"),
                            ], width="auto"),
                            dbc.Col([
                                dbc.Button("Clear All", id="clear-all", n_clicks=0, color="secondary", outline=True),
                            ], width="auto")
                        ], className="gap-2"),
                    ])
                ], className="mb-4 shadow-sm"),

                # Card 3: Options
                dbc.Card([
                    dbc.CardHeader(html.H4("3. Choose Calendar Options", className="m-0", style={"color": USAFA_NAVY})),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Academic Calendar Export", className="fw-bold", style={"color": USAFA_NAVY}),
                                dbc.RadioItems(
                                    id="academic-export-mode",
                                    options=[
                                        {"label": " Teaching appointments only", "value": "none"},
                                        {"label": " Teaching appointments + uploaded academic events", "value": "all"},
                                    ],
                                    value="none",
                                    className="mb-3",
                                ),
                                dbc.Label("Reminder for teaching appointments", className="fw-bold", style={"color": USAFA_NAVY}),
                                dbc.RadioItems(
                                    id="reminder-on",
                                    options=[{"label": " No reminder", "value": "no"}, {"label": " Reminder", "value": "yes"}],
                                    value="yes",
                                    inline=True,
                                    className="mb-3",
                                ),
                            ], md=6),
                            dbc.Col([
                                dbc.Label("Reminder minutes before class", className="fw-bold", style={"color": USAFA_NAVY}),
                                dbc.Input(id="reminder-minutes", type="number", value=15, min=0, step=5, className="mb-3", style={"maxWidth": "150px"}),
                                
                                dbc.Label("Show time as", className="fw-bold", style={"color": USAFA_NAVY}),
                                dbc.Select(
                                    id="busy-status", 
                                    options=[{"label": "Free", "value": "0"}, {"label": "Tentative", "value": "1"}, {"label": "Busy", "value": "2"}, {"label": "Out of Office", "value": "3"}], 
                                    value="2", 
                                    className="mb-3", style={"maxWidth": "250px"}
                                ),
                                
                                dbc.Checklist(
                                    id="private", 
                                    options=[{"label": " Mark appointments private", "value": "private"}], 
                                    value=[],
                                    className="mb-3"
                                ),
                            ], md=6)
                        ])
                    ])
                ], className="mb-4 shadow-sm"),

                # Card 4: Preview/Download
                dbc.Card([
                    dbc.CardHeader(html.H4("4. Preview or Download", className="m-0", style={"color": USAFA_NAVY})),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Appointments in preview", className="fw-bold", style={"color": USAFA_NAVY}),
                                dbc.Select(
                                    id="preview-limit",
                                    options=[
                                        {"label": "10 appointments", "value": "10"},
                                        {"label": "20 appointments", "value": "20"},
                                        {"label": "50 appointments", "value": "50"},
                                        {"label": "100 appointments", "value": "100"},
                                        {"label": "All appointments", "value": "all"},
                                    ],
                                    value="20",
                                    style={"maxWidth": "250px"}
                                ),
                            ], md=4, className="mb-3 mb-md-0"),
                            dbc.Col([
                                dbc.Label(html.Br(), className="d-none d-md-block"),
                                dbc.Button("Preview Events", id="preview", n_clicks=0, color="info", className="me-2 text-white"),
                                dbc.Button("Download .ics", id="download-ics", n_clicks=0, style={"backgroundColor": USAFA_NAVY, "color": "white"}),
                            ], md=8, className="d-flex align-items-end")
                        ]),
                        dcc.Download(id="download"),
                        
                        html.Div(id="alert-container", className="mt-3"),
                        html.Div(id="preview-table", className="mt-3"),
                        
                        dbc.Card([
                            dbc.CardHeader(html.Strong([html.I(className="bi bi-lightbulb text-warning me-2"), "Quick Guide: Importing to Outlook Safely"])),
                            dbc.CardBody([
                                html.P("We highly recommend reviewing the appointments in a separate calendar before merging them into your primary schedule."),
                                html.Ol([
                                    html.Li(["In Outlook, go to ", html.Strong("File > Open & Export > Import/Export"), "."]),
                                    html.Li(["Select ", html.Strong("Import an iCalendar (.ics) or vCalendar file (.vcs)"), " and click Next."]),
                                    html.Li(["Locate the file you just downloaded and click OK."]),
                                    html.Li([
                                        "When prompted, select ", 
                                        html.Strong("Open as New", style={"color": USAFA_BLUE}), 
                                        " (", html.Em("do not"), " click Import yet). This creates a temporary side-by-side calendar."
                                    ]),
                                    html.Li(["Review the dates and times for any errors. If everything looks correct, you can repeat the process and choose ", html.Strong("Import"), " to merge it with your main calendar."])
                                ], className="mb-0")
                            ])
                        ], className="mt-4 border-info"),

                        html.Div([
                            html.Small([
                                html.I(className="bi bi-info-circle me-1"),
                                "Timezone is set to ", html.Strong("America/Denver"), " for ICS generation."
                            ], className="text-muted d-block mt-3")
                        ])
                    ])
                ], className="mb-5 shadow-sm"),
            ])
        ], className="mt-4")
    ])
], style={"backgroundColor": "#F2F4F5", "minHeight": "100vh", "paddingBottom": "20px"})

@app.callback(
    Output("course-rows", "children"),
    Input("add-row", "n_clicks"),
    Input({"type": "remove-row", "index": ALL}, "n_clicks"),
    Input("clear-all", "n_clicks"),
    State("course-rows", "children"),
    prevent_initial_call=True
)
def manage_course_rows(add_clicks, remove_clicks, clear_clicks, children):
    if not children:
        children = []

    ctx_trigger = ctx.triggered_id
    if ctx_trigger == "add-row":
        children.append(make_course_row())
    elif ctx_trigger == "clear-all":
        return [make_course_row()]
    elif isinstance(ctx_trigger, dict) and ctx_trigger["type"] == "remove-row":
        remove_index = ctx_trigger["index"]
        children = [c for c in children if c["props"]["id"]["index"] != remove_index]
        if not children:
            children.append(make_course_row())
            
    return children

@app.callback(
    Output("upload-status", "children"), 
    Output("alert-container", "children", allow_duplicate=True),
    Input("calendar-upload", "contents"), 
    State("calendar-upload", "filename"),
    prevent_initial_call=True
)
def upload_status(contents, filename):
    try:
        df = logic.parse_uploaded_csv(contents)
        days, modified = logic.extract_schedule_days(df)
        source = filename if contents else f"bundled default: {logic.DEFAULT_CALENDAR_FILENAME}"
        return f"Loaded {source}: found {len(days)} M/T class days and {len(modified)} modified SOC day(s).", None
    except Exception as exc:
        return "", dbc.Alert(f"Calendar problem: {exc}", color="danger", dismissable=True)

def make_events_from_state(contents, names, periods, locations, descriptions, categories, academic_mode, reminder_value, reminder_minutes, busy_status, private_values):
    df = logic.parse_uploaded_csv(contents)
    course_rows = logic.assemble_course_rows(
        names, periods, locations, descriptions, categories,
        allow_empty=(academic_mode != "none"),
    )
    events = logic.build_events(
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
    Output("alert-container", "children"),
    Output("preview-table", "children"),
    Input("preview", "n_clicks"),
    State("calendar-upload", "contents"),
    *COURSE_STATES,
    State("academic-export-mode", "value"),
    State("preview-limit", "value"),
    State("reminder-on", "value"), State("reminder-minutes", "value"), State("busy-status", "value"), State("private", "value"),
    prevent_initial_call=True,
)
def preview_events(_n_clicks, contents, names, periods, locations, descriptions, categories, academic_mode, preview_limit_value, reminder_value, reminder_minutes, busy_status, private_values):
    try:
        df, events = make_events_from_state(contents, names, periods, locations, descriptions, categories, academic_mode, reminder_value, reminder_minutes, busy_status, private_values)
        academic_df = logic.filter_academic_rows(df, academic_mode)
        total = len(events) + len(academic_df)
        
        if total == 0:
            return dbc.Alert("No events generated. Please add courses with M/T periods.", color="warning", dismissable=True), ""
            
        preview_limit = total if preview_limit_value == "all" else max(1, int(preview_limit_value or 20))
        sample = [
            {"Type": "Teaching", "Date": logic.fmt_date(e["date"]), "Start": logic.fmt_time(e["start"]), "End": logic.fmt_time(e["end"]), "Subject": e["subject"], "Location": e["location"], "Modified SOC": "Yes" if e["modified_soc"] else ""}
            for e in events[:preview_limit]
        ]
        remaining = max(0, preview_limit - len(sample))
        for _, row in academic_df.head(remaining).iterrows():
            sample.append({
                "Type": "Academic calendar",
                "Date": logic.clean_value(row.get("Start Date", "")),
                "Start": "All day" if logic.truthy(row.get("All day event", False)) else logic.clean_value(row.get("Start Time", "")),
                "End": logic.clean_value(row.get("End Date", "")) if logic.truthy(row.get("All day event", False)) else logic.clean_value(row.get("End Time", "")),
                "Subject": logic.clean_value(row.get("Subject", "")),
                "Location": logic.clean_value(row.get("Location", "")),
                "Modified SOC": "",
            })
            
        table = dash_table.DataTable(
            data=sample,
            page_size=max(1, min(len(sample), 25)),
            style_cell={"textAlign": "left", "padding": "10px", "fontFamily": "Arial, Helvetica, sans-serif"},
            style_header={"backgroundColor": USAFA_NAVY, "color": "white", "fontWeight": "bold"},
            style_data_conditional=[{"if": {"row_index": "odd"}, "backgroundColor": "#F8F9FA"}],
            style_table={"overflowX": "auto", "border": "1px solid #dee2e6", "borderRadius": "4px"},
        )
        shown = len(sample)
        preview_text = "all appointments" if shown == total else f"the first {shown}"
        
        success_msg = f"Generated {total} events: {len(events)} teaching appointment(s) and {len(academic_df)} uploaded academic calendar event(s). Showing {preview_text}."
        alert = dbc.Alert(success_msg, color="success", dismissable=True)
        return alert, table
    except Exception as exc:
        return dbc.Alert(f"Problem: {exc}", color="danger", dismissable=True), ""

@app.callback(
    Output("download", "data"),
    Input("download-ics", "n_clicks"),
    State("calendar-upload", "contents"),
    *COURSE_STATES,
    State("academic-export-mode", "value"),
    State("reminder-on", "value"), State("reminder-minutes", "value"), State("busy-status", "value"), State("private", "value"),
    prevent_initial_call=True,
)
def download_file(_n_ics, contents, names, periods, locations, descriptions, categories, academic_mode, reminder_value, reminder_minutes, busy_status, private_values):
    df, events = make_events_from_state(contents, names, periods, locations, descriptions, categories, academic_mode, reminder_value, reminder_minutes, busy_status, private_values)
    return dict(content=logic.events_to_ics(events, df, academic_mode), filename="usafa_schedule.ics", type="text/calendar")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8050")), debug=False)
