import calendar

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_widget

from services.grassland_health import (
    STATUS_COLORS,
    county_health,
    county_month_comparison,
    county_signal_series,
    movement_recommendations,
    ward_health_geojson,
)
from services.gee_climate import climate_data
from services.grassland_tiles import MAX_ZOOM, MIN_ZOOM, TILE_BOUNDS, TILE_URL
from .data import AOIS
from .loading import loading_frame
from .maplibre import map_container


AVAILABLE_DATES = climate_data()[["date"]].drop_duplicates().sort_values("date")
LATEST_DATE = AVAILABLE_DATES["date"].max()
YEAR_CHOICES = {
    str(year): str(year)
    for year in sorted(AVAILABLE_DATES["date"].dt.year.unique(), reverse=True)
}
LATEST_MONTH_CHOICES = {
    str(month): calendar.month_name[month]
    for month in sorted(
        AVAILABLE_DATES.loc[AVAILABLE_DATES["date"].dt.year == LATEST_DATE.year, "date"].dt.month.unique()
    )
}


def _gci_signal(icon: str, weight: str, name: str, description: str, direction: str):
    return ui.div(
        ui.div(ui.tags.i(class_=f"bi {icon}"), ui.span(weight), class_="gci-signal-head"),
        ui.strong(name),
        ui.p(description),
        ui.span(direction, class_="gci-direction"),
        class_="gci-signal-card",
    )


def gci_context_panel():
    return ui.tags.section(
        ui.div(
            ui.div(
                ui.span("HOW TO READ THE INDEX", class_="gci-kicker"),
                ui.h2("One grazing score, four environmental signals"),
                ui.p("GCI combines normalized satellite and climate observations into a 0–100 monthly ward score. Higher values indicate more favorable grazing conditions."),
            ),
            ui.div(
                ui.span("0", class_="gci-score-edge"),
                ui.div(ui.strong("GCI"), ui.span("Monthly ward condition")),
                ui.span("100", class_="gci-score-edge"),
                class_="gci-score-mark",
            ),
            class_="gci-context-head",
        ),
        ui.div(
            _gci_signal("bi-flower1", "35%", "NDVI", "Vegetation greenness and photosynthetic vigor from satellite imagery.", "Greener vegetation raises GCI"),
            _gci_signal("bi-cloud-rain", "25%", "Rainfall", "Monthly precipitation supporting pasture growth and recovery.", "More available rainfall raises GCI"),
            _gci_signal("bi-thermometer-sun", "20%", "Temperature", "Land-surface heat pressure affecting vegetation and water demand.", "Reverse scored · excess heat lowers GCI"),
            _gci_signal("bi-grid-3x3-gap", "20%", "Landsat red-band MSDI", "A 3×3 moving standard deviation measuring fine-scale variation in red reflectance.", "Reverse scored · higher variability lowers GCI"),
            class_="gci-signal-grid",
        ),
        ui.div(
            ui.code("GCI = 0.35(NDVI) + 0.25(rainfall) + 0.20(reversed temperature) + 0.20(reversed MSDI)"),
            ui.span("All components are normalized to a common 0–100 scale before weighting."),
            class_="gci-formula",
        ),
        ui.div(
            *[
                ui.div(
                    ui.span(class_="gci-class-color", style=f"background:{STATUS_COLORS[label]}"),
                    ui.strong(label),
                    ui.span(score_range),
                    class_="gci-class-item",
                )
                for label, score_range in [
                    ("Very poor", "0–19.9"),
                    ("Poor", "20–39.9"),
                    ("Moderate", "40–59.9"),
                    ("Good", "60–79.9"),
                    ("Very good", "80–100"),
                ]
            ],
            class_="gci-class-scale",
        ),
        class_="gci-context-panel",
    )


@module.ui
def drought_monitor_ui():
    return ui.div(
        ui.div(
            ui.div(
                ui.tags.span("GRASSLAND EARLY ACTION", class_="eyebrow"),
                ui.h1("Grassland health intelligence"),
                ui.p("Track the supplied Grazing Condition Index across wards and identify areas requiring attention or offering stronger conditions."),
                ui.div(
                    ui.span(ui.tags.i(class_="bi bi-flower1"), " Ward-level analysis"),
                    ui.span("GCI · NDVI · rainfall · temperature"),
                    class_="hero-chips light-chips",
                ),
            ),
            class_="page-hero module-hero resource-hero drought-hero",
        ),
        loading_frame(ui.output_ui("health_summary"), "metrics", 112),
        gci_context_panel(),
        ui.div(
            ui.card(
                ui.card_header(
                    ui.div(
                        ui.span("Ward grazing conditions"),
                        ui.output_ui("map_date"),
                        class_="map-title-row",
                    ),
                    ui.div(
                        ui.input_select("aoi", "Focus county", AOIS),
                        ui.input_select("year", "Year", YEAR_CHOICES, selected=str(LATEST_DATE.year)),
                        ui.input_select("month", "Month", LATEST_MONTH_CHOICES, selected=str(LATEST_DATE.month)),
                        class_="map-filter-bar",
                    ),
                ),
                loading_frame(ui.output_ui("health_map"), "map", 540),
                ui.div(
                    *[
                        ui.span(ui.span(class_="health-dot", style=f"background:{color}"), label)
                        for label, color in STATUS_COLORS.items()
                    ],
                    ui.span(ui.span(class_="raster-swatch"), "ESA grassland cover"),
                    class_="grassland-legend",
                ),
                class_="panel-card map-card climate-map-card",
            ),
            ui.div(
                ui.card(
                    ui.card_header("Monthly signals vs long-term average", ui.output_ui("chart_note")),
                    loading_frame(output_widget("signal_chart"), "chart", 450),
                    class_="panel-card chart-card grassland-chart-card",
                ),
                ui.card(
                    ui.card_header("Grazing movement guidance"),
                    loading_frame(ui.output_ui("movement_guidance"), "copy", 230),
                    class_="panel-card movement-card",
                ),
                class_="climate-side-panel",
            ),
            class_="drought-workspace",
        ),
        ui.card(
            ui.card_header("Ward assessment", ui.span("Selected monthly GCI observation with supporting indicators", class_="header-note")),
            loading_frame(ui.output_data_frame("ward_table"), "table", 440),
            class_="panel-card observations-card",
        ),
        ui.div(
            ui.tags.i(class_="bi bi-info-circle"),
            ui.span("Movement guidance is a screening signal, not a movement instruction. Confirm water access, land tenure, conflict risk and local authority advice before action."),
            class_="method-note",
        ),
        class_="page-shell drought-page",
    )


@module.server
def drought_monitor_server(input, output, session):
    @reactive.effect
    @reactive.event(input.year)
    def sync_month_choices():
        months = sorted(
            AVAILABLE_DATES.loc[
                AVAILABLE_DATES["date"].dt.year == int(input.year()), "date"
            ].dt.month.unique()
        )
        selected = input.month() if input.month() and int(input.month()) in months else str(max(months))
        ui.update_select(
            "month",
            choices={str(month): calendar.month_name[month] for month in months},
            selected=selected,
            session=session,
        )

    @reactive.calc
    def selected_date():
        year = int(input.year())
        valid_months = sorted(
            AVAILABLE_DATES.loc[AVAILABLE_DATES["date"].dt.year == year, "date"].dt.month.unique()
        )
        requested_month = int(input.month()) if input.month() else max(valid_months)
        month = requested_month if requested_month in valid_months else max(valid_months)
        return pd.Timestamp(year=year, month=month, day=1)

    @reactive.calc
    def selected_health():
        return county_health(input.aoi(), AOIS, selected_date())

    @render.ui
    def health_map():
        selected_name = AOIS[input.aoi()]
        center = (
            (TILE_BOUNDS[0] + TILE_BOUNDS[2]) / 2,
            (TILE_BOUNDS[1] + TILE_BOUNDS[3]) / 2,
        )
        geojson = ward_health_geojson(selected_name, selected_date())
        return map_container(
            [], center=center, zoom=6.2, height=540,
            label="Ward Grazing Condition Index map", geojson=geojson,
            raster_tiles=TILE_URL, raster_bounds=TILE_BOUNDS,
            raster_minzoom=MIN_ZOOM, raster_maxzoom=MAX_ZOOM,
            fit_geojson=True,
        )

    @render.ui
    def map_date():
        label = "Latest analysis" if selected_date() == LATEST_DATE else "Historical analysis"
        return ui.span(selected_date().strftime(f"{label} · %B %Y"), class_="header-note data-date")

    @render.ui
    def health_summary():
        frame = selected_health()
        very_poor = int((frame["condition"] == "Very poor").sum())
        poor = int((frame["condition"] == "Poor").sum())
        good = int((frame["condition"] == "Good").sum())
        very_good = int((frame["condition"] == "Very good").sum())
        median_score = frame["health_score"].median()
        cards = [
            ("Very poor", str(very_poor), "Immediate field verification"),
            ("Poor", str(poor), "Priority monitoring"),
            ("Good / very good", str(good + very_good), "Potential local alternatives"),
            ("Median GCI", f"{median_score:.1f}", AOIS[input.aoi()]),
        ]
        return ui.div(*[
            ui.div(
                ui.span(label, class_="metric-label"),
                ui.strong(value, style=f"color:{STATUS_COLORS['Very poor']}" if label == "Very poor" else None),
                ui.span(note, class_="metric-note"),
                class_="metric-card",
            )
            for label, value, note in cards
        ], class_="metric-grid")

    @render.ui
    def chart_note():
        frame = county_signal_series(AOIS[input.aoi()])
        baseline_years = frame["date"].dt.year
        baseline_label = f"LTA {baseline_years.min()}–{baseline_years.max()}" if not baseline_years.empty else "No baseline"
        return ui.span(
            f"{AOIS[input.aoi()]} · {input.year()} vs {baseline_label}",
            class_="header-note",
        )

    @render_widget
    def signal_chart():
        selected_year = int(input.year())
        frame = county_month_comparison(AOIS[input.aoi()], selected_year)
        month_labels = [calendar.month_abbr[month] for month in frame["month"]]
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=("NDVI", "Grazing Condition Index", "Rainfall (mm)", "Land temperature (°C)"),
            vertical_spacing=0.18, horizontal_spacing=0.12,
        )
        traces = [
            ("NDVI", 1, 1, "#23977d"),
            ("GCI", 1, 2, "#5a9b52"),
            ("prcp", 2, 1, "#3d83b8"),
            ("lst", 2, 2, "#df7955"),
        ]
        for trace_index, (column, row, col, color) in enumerate(traces):
            fig.add_trace(go.Scatter(
                x=month_labels, y=frame[f"{column}_average"], mode="lines",
                name="Long-term average", legendgroup="average", showlegend=trace_index == 0,
                line={"color": "#82918c", "width": 2, "dash": "dash", "shape": "spline", "smoothing": 0.65},
                fill="tozeroy", fillcolor="rgba(130,145,140,.14)",
                hovertemplate=f"%{{x}}<br>Long-term average: %{{y:.2f}}<extra></extra>",
            ), row=row, col=col)
            fig.add_trace(go.Scatter(
                x=month_labels, y=frame[f"{column}_selected"], mode="lines+markers",
                name=str(selected_year), legendgroup="selected", showlegend=trace_index == 0,
                line={"color": color, "width": 2.5, "shape": "spline", "smoothing": 0.65},
                marker={"color": color, "size": 6},
                hovertemplate=f"%{{x}} {selected_year}<br>{column.upper()}: %{{y:.2f}}<extra></extra>",
            ), row=row, col=col)
        fig.update_layout(
            height=450, margin={"l": 45, "r": 20, "t": 45, "b": 35},
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font={"family": "DM Sans", "color": "#52635f"},
            legend={"orientation": "h", "x": 0, "y": 1.16, "title": None},
            hovermode="x unified",
        )
        fig.update_xaxes(gridcolor="#e6ebe8", showgrid=True, categoryorder="array", categoryarray=month_labels)
        fig.update_yaxes(gridcolor="#e6ebe8", zeroline=False)
        return fig

    @render.ui
    def movement_guidance():
        frame = selected_health()
        declining = frame[frame["condition"].isin(["Very poor", "Poor"])].sort_values("health_score")
        recommendations = movement_recommendations(AOIS[input.aoi()], selected_date())
        if declining.empty:
            return ui.div(
                ui.span("NO STRONG DECLINE SIGNAL", class_="guidance-kicker"),
                ui.h3("Maintain local monitoring"),
                ui.p("No wards in the selected county are currently classified as poor or very poor."),
                class_="guidance-content",
            )
        origin_names = ", ".join(declining["ADM3_EN"].head(4))
        destination_items = [
            ui.div(
                ui.span(f"{index:02d}", class_="destination-rank"),
                ui.div(
                    ui.strong(f"{item['ADM3_EN']} · {item['ADM1_EN']}"),
                    ui.p(f"{item['relation']} · approximately {item['distance_km']:.0f} km · health {item['score']:.0f}/100"),
                ),
                class_="destination-item",
            )
            for index, item in enumerate(recommendations, 1)
        ]
        return ui.div(
            ui.span("EARLY-ACTION SCREEN", class_="guidance-kicker"),
            ui.h3(f"Grazing condition is poor around {origin_names}"),
            ui.p("Assess good or very good wards within the county or directly across its border, limited to roughly 150 km from a poor-condition ward:"),
            ui.div(
                *destination_items,
                ui.p("No suitable stable or stronger ward was found locally or directly across the county border.", class_="no-destination") if not destination_items else None,
                class_="destination-list",
            ),
            class_="guidance-content",
        )

    @render.data_frame
    def ward_table():
        frame = selected_health().copy()
        frame = frame[[
            "ADM3_EN", "condition", "health_score", "ndvi", "ndvi_change",
            "rainfall", "rainfall_anomaly_pct", "temperature", "msdi",
        ]].sort_values("health_score")
        frame.columns = [
            "Ward", "GCI class", "GCI", "NDVI", "NDVI change",
            "Rainfall (mm)", "Rainfall anomaly (%)", "Temperature (°C)", "MSDI",
        ]
        numeric = ["GCI", "NDVI", "NDVI change", "Rainfall (mm)", "Rainfall anomaly (%)", "Temperature (°C)", "MSDI"]
        frame[numeric] = frame[numeric].round(2)
        return render.DataGrid(frame, height="440px", width="100%")
