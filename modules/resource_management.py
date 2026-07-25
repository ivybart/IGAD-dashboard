import plotly.graph_objects as go
from shiny import module, render, ui
from shinywidgets import output_widget, render_widget

from .data import AOIS, FACILITY_POINTS, get_facilities, get_resources
from .loading import loading_frame
from .maplibre import map_container


@module.ui
def resource_management_ui():
    return ui.div(
        ui.div(
            ui.div(
                ui.tags.span("FIELD OPERATIONS", class_="eyebrow"),
                ui.h1("Resource command"),
                ui.p("A live operating picture for facilities, stocks and deployment readiness."),
                ui.div(
                    ui.span(ui.tags.i(class_="bi bi-broadcast"), " Operational view"),
                    ui.span("Updated today"),
                    class_="hero-chips light-chips",
                ),
            ),
            ui.div(ui.input_select("aoi", "Operational area", AOIS), class_="filter-bar compact command-filter"),
            class_="page-hero module-hero resource-hero",
        ),
        loading_frame(ui.output_ui("resource_summary"), "metrics", 112),
        ui.div(
            ui.card(
                ui.card_header("Asset network", ui.span("Select a marker for facility details", class_="header-note")),
                loading_frame(ui.output_ui("resource_map"), "map", 680),
                ui.div(
                    ui.span(ui.span(class_="asset-dot operational"), "Operational"),
                    ui.span(ui.span(class_="asset-dot attention"), "Needs attention"),
                    class_="asset-legend",
                ),
                class_="panel-card map-card operations-map-card",
            ),
            ui.div(
                ui.card(
                    ui.card_header("Readiness profile", ui.span("Availability by resource", class_="header-note")),
                    loading_frame(output_widget("readiness"), "chart", 330),
                    class_="panel-card chart-card readiness-card",
                ),
                ui.div(
                    ui.div(ui.tags.i(class_="bi bi-exclamation-diamond"), ui.div(ui.span("NEXT ACTION", class_="action-kicker"), ui.strong("Replenish low-stock hubs"), ui.p("Prioritise water and relief assets below 40% readiness.")), class_="priority-callout"),
                    ui.div(ui.span("01"), ui.div(ui.strong("Validate"), ui.p("Confirm facility status with field focal points.")), class_="action-step"),
                    ui.div(ui.span("02"), ui.div(ui.strong("Route"), ui.p("Assign the nearest available operational asset.")), class_="action-step"),
                    class_="operations-brief",
                ),
                class_="operations-side",
            ),
            class_="operations-workspace",
        ),
        ui.card(
            ui.card_header("Facility register", ui.span("Searchable operational snapshot", class_="header-note")),
            loading_frame(ui.output_data_frame("facilities"), "table", 360),
            class_="panel-card registry-card",
        ),
        class_="page-shell operations-page",
    )


@module.server
def resource_management_server(input, output, session):
    @render.ui
    def resource_map():
        points = FACILITY_POINTS.copy()
        points["color"] = points["status"].map(lambda status: "#42c491" if status == "Operational" else "#f0785f")
        points["size"] = 17 + points["capacity"] / 7
        points["popup"] = points.apply(lambda row: f"<strong>{row['name']}</strong><span>{row['type']}</span><hr><span>Status <b>{row['status']}</b></span><span>Capacity <b>{row['capacity']}%</b></span>", axis=1)
        return map_container(points, center=(40.0, 0.3), zoom=4.6, height=680, label="Resource facility map")

    @render.ui
    def resource_summary():
        resources = get_resources(input.aoi())
        facilities = get_facilities(input.aoi())
        readiness = int(resources["availability"].mean())
        online = int(resources["operational"].sum())
        low = int((resources["availability"] < 40).sum())
        cards = [
            ("bi-box-seam", "Assets online", str(online), "Across tracked facilities"),
            ("bi-speedometer2", "Average readiness", f"{readiness}%", "All resource groups"),
            ("bi-exclamation-triangle", "Immediate priorities", str(low), "Below 40% readiness"),
            ("bi-geo-alt", "Facilities tracked", str(len(facilities)), AOIS[input.aoi()]),
        ]
        return ui.div(*[
            ui.div(ui.div(ui.tags.i(class_=f"bi {icon}"), class_="summary-icon"), ui.div(ui.span(label), ui.strong(value), ui.span(note, class_="summary-note")), class_="summary-card")
            for icon, label, value, note in cards
        ], class_="summary-ribbon")

    @render_widget
    def readiness():
        df = get_resources(input.aoi()).sort_values("availability")
        colors = ["#f0785f" if value < 40 else "#efb84e" if value < 60 else "#28a67a" for value in df["availability"]]
        fig = go.Figure(go.Bar(x=df["availability"], y=df["resource"], orientation="h", marker={"color": colors, "cornerradius": 9}, text=[f"{v}%" for v in df["availability"]], textposition="outside", hovertemplate="%{y}: %{x}% ready<extra></extra>"))
        fig.update_layout(height=330, margin={"l": 15, "r": 48, "t": 10, "b": 30}, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font={"family": "DM Sans", "color": "#52635f"}, xaxis={"range": [0, 100], "ticksuffix": "%", "gridcolor": "#e8eeeb", "zeroline": False}, yaxis={"title": ""}, showlegend=False)
        return fig

    @render.data_frame
    def facilities():
        return render.DataGrid(get_facilities(input.aoi()), height="360px", width="100%")
