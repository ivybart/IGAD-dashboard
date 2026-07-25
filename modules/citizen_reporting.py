from datetime import datetime

from shiny import module, reactive, render, ui

from .data import AOIS, REPORT_POINTS
from .loading import loading_frame
from .maplibre import map_container


INITIAL_REPORTS = [
    {"type": "Water shortage", "area": "Makueni County", "village": "Kathonzweni", "ward": "Kathonzweni", "latitude": -2.21, "longitude": 37.81, "details": "Community water point has been dry for three days.", "time": "Today · 09:40", "status": "New"},
    {"type": "Livestock health", "area": "BRCiS Somalia", "village": "", "ward": "", "latitude": 1.72, "longitude": 44.76, "details": "Unusual livestock movement reported near the grazing corridor.", "time": "Yesterday · 16:15", "status": "Verified"},
]


@module.ui
def citizen_reporting_ui():
    return ui.div(
        ui.div(
            ui.div(
                ui.tags.span("COMMUNITY SIGNALS", class_="eyebrow"),
                ui.h1("Local insight, mapped"),
                ui.p("Capture trusted observations where they happen and move them into the response workflow."),
                ui.div(ui.span("●", class_="live-dot"), " Reporting channel online", class_="channel-status hero-channel"),
            ),
            ui.div(
                ui.div(ui.tags.i(class_="bi bi-shield-check"), ui.div(ui.strong("Privacy first"), ui.span("No personal names required")), class_="hero-assurance"),
                ui.div(ui.tags.i(class_="bi bi-geo-alt"), ui.div(ui.strong("Location aware"), ui.span("GPS or manual coordinates")), class_="hero-assurance"),
                class_="assurance-stack",
            ),
            class_="page-hero module-hero citizen-hero",
        ),
        ui.div(
            ui.card(
                ui.card_header("Community signal map", ui.output_text("count")),
                loading_frame(ui.output_ui("reports_map"), "map", 680),
                ui.div(ui.span(ui.span(class_="signal-dot new"), "New / priority"), ui.span(ui.span(class_="signal-dot verified"), "Verified"), class_="signal-legend"),
                class_="panel-card map-card citizen-map-card",
            ),
            ui.card(
                ui.card_header(ui.div(ui.span("NEW SIGNAL", class_="form-step"), ui.span("Submit a field report"))),
                ui.div(ui.tags.i(class_="bi bi-info-circle"), "Share only what responders need. Fields marked optional can be left blank.", class_="form-intro"),
                ui.input_select("area", "Administrative area", AOIS),
                ui.div(ui.input_text("village", "Village / settlement", placeholder="If known"), ui.input_text("ward", "Ward", placeholder="If known"), class_="location-name-grid"),
                ui.div(
                    ui.div(ui.tags.i(class_="bi bi-crosshair"), ui.div(ui.strong("Are you at the report location?"), ui.p("Capture your device coordinates to improve response accuracy.")), class_="geo-copy"),
                    ui.input_action_button("capture_location", "Use my location", class_="btn-location"),
                    ui.div(ui.input_text("latitude", "Latitude", placeholder="Not captured"), ui.input_text("longitude", "Longitude", placeholder="Not captured"), class_="coordinate-grid"),
                    ui.div("Coordinates are optional and can be reviewed before sending.", class_="location-status", aria_live="polite"),
                    class_="geo-capture",
                ),
                ui.input_select("type", "Report type", ["Water shortage", "Livestock health", "Crop stress", "Displacement", "Market prices", "Other"]),
                ui.input_text_area("details", "What are you observing?", placeholder="Describe what happened, where, and when…", rows=5),
                ui.input_select("urgency", "Urgency", ["Routine", "Priority", "Critical"]),
                ui.input_action_button("submit", ui.tags.span("Send for verification ", ui.tags.i(class_="bi bi-arrow-right")), class_="btn-submit"),
                ui.output_ui("confirmation"),
                ui.div(ui.tags.i(class_="bi bi-shield-lock"), ui.span("Reports are reviewed before informing operational decisions."), class_="form-trust"),
                class_="panel-card report-form modern-report-form",
            ),
            class_="citizen-workspace",
        ),
        ui.div(
            ui.div(ui.tags.span("VERIFICATION QUEUE", class_="eyebrow"), ui.h2("Latest community reports"), ui.p("A transparent stream of incoming and reviewed observations.")),
            ui.card(loading_frame(ui.output_ui("report_feed"), "feed", 260), class_="panel-card feed-card modern-feed"),
            class_="feed-section",
        ),
        class_="page-shell citizen-page",
    )


@module.server
def citizen_reporting_server(input, output, session):
    reports = reactive.value(list(INITIAL_REPORTS))
    message = reactive.value("")

    @render.ui
    def reports_map():
        geolocated = [item for item in reports() if item.get("latitude") is not None and item.get("longitude") is not None]
        points = REPORT_POINTS.iloc[0:0].copy()
        for item in geolocated:
            points.loc[len(points)] = {
                "name": item.get("village") or item["area"],
                "type": item["type"],
                "lat": item["latitude"],
                "lon": item["longitude"],
                "status": item["status"],
            }
        points["color"] = points["status"].map(lambda status: "#c94b4b" if status in ("New", "Priority") else "#27866f")
        points["size"] = 18
        points["popup"] = points.apply(lambda row: f"<strong>{row['type']}</strong><span>{row['name']}</span><hr><span>Status <b>{row['status']}</b></span>", axis=1)
        return map_container(points, center=(36.8219, -1.2921), zoom=6.0, height=680, label="Community reports and current location map", geolocate=True)

    @reactive.effect
    @reactive.event(input.submit)
    def _submit():
        details = input.details().strip()
        if not details:
            message.set("Please add a short description before sending.")
            return
        try:
            latitude = float(input.latitude()) if input.latitude().strip() else None
            longitude = float(input.longitude()) if input.longitude().strip() else None
            if latitude is not None and not -90 <= latitude <= 90:
                raise ValueError
            if longitude is not None and not -180 <= longitude <= 180:
                raise ValueError
        except ValueError:
            message.set("Please enter valid latitude and longitude values.")
            return
        updated = list(reports())
        updated.insert(0, {"type": input.type(), "area": AOIS[input.area()], "village": input.village().strip(), "ward": input.ward().strip(), "latitude": latitude, "longitude": longitude, "details": details, "time": datetime.now().strftime("Today · %H:%M"), "status": input.urgency()})
        reports.set(updated)
        message.set("Report received and queued for verification.")
        ui.update_text_area("details", value="", session=session)
        ui.update_text("village", value="", session=session)
        ui.update_text("ward", value="", session=session)
        ui.update_text("latitude", value="", session=session)
        ui.update_text("longitude", value="", session=session)

    @render.ui
    def confirmation():
        return ui.p(message(), class_="form-message") if message() else None

    @render.text
    def count():
        return f"{len(reports())} reports"

    @render.ui
    def report_feed():
        cards = []
        for item in reports():
            place = " · ".join(part for part in [item.get("village"), item.get("ward"), item["area"]] if part)
            coords = f"{item['latitude']:.5f}, {item['longitude']:.5f}" if item.get("latitude") is not None else "Location not captured"
            cards.append(ui.div(ui.div(ui.span(item["type"], class_="report-type"), ui.span(item["status"], class_="report-status")), ui.p(item["details"]), ui.span(f"{place} · {item['time']}", class_="report-meta"), ui.div(ui.tags.i(class_="bi bi-geo-alt"), coords, class_="report-coordinates"), class_="report-item"))
        return ui.div(*cards, class_="report-list")
