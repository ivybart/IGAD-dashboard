import copy

import plotly.graph_objects as go
from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_widget

from services.gee_climate import (
    INDICATORS as INDICATOR_META,
    county_name,
    county_series,
    drought_phase,
    format_value,
    indicator_geojson,
    latest_county_metrics,
)
from .data import AOIS, INDICATORS, STATUS_COLORS
from .loading import loading_frame
from .maplibre import map_container


@module.ui
def drought_monitor_ui():
    return ui.div(
        ui.div(
            ui.div(
                ui.tags.span("GEE CLIMATE ARCHIVE", class_="eyebrow"),
                ui.h1("Drought intelligence"),
                ui.p("Explore ward observations through April 2026, aggregated into county-level signals for faster decisions."),
                ui.div(
                    ui.span(ui.tags.i(class_="bi bi-layers"), " County intelligence"),
                    ui.span("Updated April 2026"),
                    class_="hero-chips light-chips",
                ),
            ),
            ui.div(
                ui.input_select("aoi", "Focus county", AOIS),
                ui.input_select("indicator", "Map & chart indicator", INDICATORS, selected="cdi3"),
                class_="filter-bar two-fields command-filter",
            ),
            class_="page-hero module-hero resource-hero drought-hero",
        ),
        loading_frame(ui.output_ui("status_strip"), "metrics", 112),
        ui.div(
            ui.card(
                ui.card_header("County indicator map", ui.output_ui("map_date")),
                loading_frame(ui.output_ui("area_map"), "map", 680),
                ui.output_ui("map_legend"),
                class_="panel-card map-card climate-map-card",
            ),
            ui.div(
                ui.card(ui.card_header("Monthly trajectory", ui.output_ui("chart_note")), loading_frame(output_widget("trend"), "chart", 390), class_="panel-card chart-card climate-chart-card"),
                ui.card(ui.card_header("Decision cue"), loading_frame(ui.output_ui("brief"), "copy", 190), class_="panel-card action-card"),
                class_="climate-side-panel",
            ),
            class_="drought-workspace",
        ),
        ui.card(
            ui.card_header("Recent observations", ui.span("Area-weighted from ward records in the supplied GEE export", class_="header-note")),
            loading_frame(ui.output_data_frame("table"), "table", 340),
            class_="panel-card observations-card",
        ),
        class_="page-shell drought-page",
    )


@module.server
def drought_monitor_server(input, output, session):
    @reactive.calc
    def series():
        return county_series(input.aoi(), input.indicator(), 36)

    @reactive.calc
    def metrics():
        return latest_county_metrics(input.aoi())

    @reactive.calc
    def status():
        return drought_phase(metrics()["cdi3"])

    @render.ui
    def area_map():
        geojson, _ = indicator_geojson(input.indicator())
        geojson = copy.deepcopy(geojson)
        selected = county_name(input.aoi())
        for feature in geojson["features"]:
            feature["properties"]["selected"] = feature["properties"]["ADM1_EN"] == selected
        return map_container(
            [], center=(38.05, 0.05), zoom=5.05, height=680,
            label=f"County map coloured by {INDICATORS[input.indicator()]}", geojson=geojson,
        )

    @render.ui
    def map_date():
        _, legend = indicator_geojson(input.indicator())
        return ui.span(legend["date"].strftime("Latest · %B %Y"), class_="header-note data-date")

    @render.ui
    def map_legend():
        _, legend = indicator_geojson(input.indicator())
        gradient = ", ".join(legend["palette"])
        return ui.div(
            ui.div(ui.strong(INDICATOR_META[input.indicator()]["short"]), ui.span(legend["label"])),
            ui.div(
                ui.span(format_value(input.indicator(), legend["min"])),
                ui.span(class_="legend-gradient", style=f"background:linear-gradient(90deg,{gradient})"),
                ui.span(format_value(input.indicator(), legend["max"])),
                class_="legend-scale",
            ),
            ui.tags.span("County colours use the latest area-weighted ward observations. Select another indicator to redraw the map.", class_="legend-help"),
            class_="indicator-legend",
        )

    @render.ui
    def status_strip():
        current = status()
        selected_value = metrics()[input.indicator()]
        cards = [
            ("Drought phase", current, "Classified from CDI-3"),
            (INDICATOR_META[input.indicator()]["short"], format_value(input.indicator(), selected_value), "Latest county mean"),
            ("CDI-3", format_value("cdi3", metrics()["cdi3"]), "Three-month condition"),
            ("Ward coverage", str(metrics()["wards"]), metrics()["date"].strftime("Observed %b %Y")),
        ]
        return ui.div(*[
            ui.div(
                ui.span(label, class_="metric-label"),
                ui.strong(value, style=f"color:{STATUS_COLORS.get(current, '#52635f')}" if label == "Drought phase" else None),
                ui.span(note, class_="metric-note"), class_="metric-card",
            ) for label, value, note in cards
        ], class_="metric-grid")

    @render.ui
    def chart_note():
        return ui.span(f"{county_name(input.aoi())} · 36 months", class_="header-note")

    @render_widget
    def trend():
        frame = series()
        definition = INDICATOR_META[input.indicator()]
        fig = go.Figure(go.Scatter(
            x=frame["date"], y=frame["value"], mode="lines+markers",
            line={"color": "#1d7c72", "width": 3.2, "shape": "spline"},
            marker={"size": 6, "color": "#f3b746", "line": {"color": "#fff", "width": 1.5}},
            fill="tozeroy", fillcolor="rgba(29,124,114,.09)",
            hovertemplate=f"%{{x|%b %Y}}<br>{definition['short']}: %{{y:.3f}}<extra></extra>",
        ))
        fig.update_layout(
            height=390, margin={"l": 55, "r": 22, "t": 20, "b": 45},
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font={"family": "DM Sans", "color": "#52635f"}, hovermode="x unified",
            xaxis={"gridcolor": "#e6ebe8", "showline": False},
            yaxis={"gridcolor": "#e6ebe8", "title": definition["short"], "zeroline": False},
            showlegend=False,
        )
        return fig

    @render.ui
    def brief():
        current = status()
        copy_by_phase = {
            "Normal": ("Maintain readiness", "Conditions are comparatively stable. Keep routine field validation and asset checks active."),
            "Watch": ("Verify local signals", "Contact ward focal points and inspect priority water sources within the next seven days."),
            "Alert": ("Pre-position support", "Prepare water, livelihood and nutrition support while validating the most stressed wards."),
            "Warning": ("Activate protocols", "Prioritise emergency water access, rapid assessment and coordinated response."),
            "No data": ("Validate the feed", "The latest period has insufficient values for a CDI-3 classification."),
        }
        title, body = copy_by_phase[current]
        return ui.div(
            ui.div(ui.span(current.upper(), class_="status-pill", style=f"background:{STATUS_COLORS.get(current, '#73817c')}"), ui.span(metrics()["landscape"], class_="brief-landscape"), class_="brief-topline"),
            ui.h3(title), ui.p(body), ui.hr(),
            ui.span(f"For {county_name(input.aoi())} · based on {metrics()['wards']} ward records in {metrics()['date']:%B %Y}", class_="brief-note"),
            class_="brief-content",
        )

    @render.data_frame
    def table():
        frame = series().copy().sort_values("date", ascending=False).head(18)
        frame["date"] = frame["date"].dt.strftime("%B %Y")
        frame["value"] = frame["value"].round(3)
        frame.columns = ["Month", INDICATOR_META[input.indicator()]["short"], "Wards"]
        return render.DataGrid(frame, height="340px", width="100%")
