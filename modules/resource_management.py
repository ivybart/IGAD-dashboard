"""County planning reports and GeoPackage-backed resource registration."""

from __future__ import annotations

import calendar
from html import escape
from functools import lru_cache

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_widget

from services.gee_climate import climate_data
from services.county_report_pdf import build_county_report_pdf
from services.kenya_geocoding import get_kenya_place, kenya_place_choices
from services.resource_inventory import (
    GEOPACKAGE_PATH,
    RESOURCE_STATUSES,
    RESOURCE_TYPES,
    county_boundary_geojson,
    list_resources,
    save_resource,
)

from .data import AOIS
from .loading import loading_frame
from .maplibre import map_container


AVAILABLE_DATES = climate_data()[["date"]].drop_duplicates().sort_values("date")
LATEST_DATE = AVAILABLE_DATES["date"].max()
YEAR_CHOICES = {
    str(year): str(year)
    for year in sorted(AVAILABLE_DATES["date"].dt.year.unique(), reverse=True)
}
RESOURCE_COLORS = {
    "Grass seed bank": "#9bbf56",
    "Borehole": "#3f8fc4",
    "Nursery": "#2f9b73",
    "Animal watering point": "#df9850",
}
REPORT_METRICS = {
    "GCI": ("GCI", "", (0, 100)),
    "NDVI": ("NDVI", "", (-1, 1)),
    "prcp": ("Rainfall", "mm", (0, None)),
    "lst": ("Temperature", "°C", (None, None)),
    "msdi": ("MSDI", "", (0, None)),
}
KENYA_PLACE_CHOICES = kenya_place_choices()


def _weighted(frame: pd.DataFrame, column: str) -> float:
    valid = frame[[column, "area"]].dropna()
    if valid.empty:
        return float("nan")
    return float(np.average(valid[column], weights=valid["area"]))


def _condition(score: float) -> str:
    if not np.isfinite(score):
        return "No data"
    return ["Very poor", "Poor", "Moderate", "Good", "Very good"][min(4, max(0, int(score // 20)))]


def _planning_actions(summary: dict, resource_total: int) -> list[str]:
    metrics = summary["metrics"]
    baseline = summary["baseline"]
    priority = int(summary["classes"].get("Very poor", 0) + summary["classes"].get("Poor", 0))
    rainfall_delta = metrics["prcp"] - baseline.get("prcp", np.nan)
    ndvi_delta = metrics["NDVI"] - baseline.get("NDVI", np.nan)
    actions: list[str] = []
    if priority:
        actions.append(f"Field-check grazing and water access in the {priority} poor or very poor wards.")
    if np.isfinite(rainfall_delta) and rainfall_delta < 0:
        actions.append("Rainfall is below the long-term value for this month; verify borehole and animal watering point reliability.")
    if np.isfinite(ndvi_delta) and ndvi_delta < 0:
        actions.append("Vegetation greenness is below its monthly reference; assess grass seed banks and nurseries for restoration support.")
    if resource_total == 0:
        actions.append("No resources are registered for this county yet; begin by mapping priority water and restoration assets.")
    if not actions:
        actions.append("Conditions are comparatively stable; maintain asset checks and update the inventory when availability changes.")
    return actions


@lru_cache(maxsize=8)
def _county_monthly_series(county: str) -> pd.DataFrame:
    subset = climate_data()[climate_data()["ADM1_EN"] == county]
    rows = []
    for date, frame in subset.groupby("date"):
        rows.append({"date": date, **{column: _weighted(frame, column) for column in REPORT_METRICS}})
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def _next_month_forecast(county: str, selected_date: pd.Timestamp) -> dict:
    """OLS trend forecast with a 95% prediction range from prior instances of the target month."""
    target_date = selected_date + pd.DateOffset(months=1)
    series = _county_monthly_series(county)
    history = series[(series["date"].dt.month == target_date.month) & (series["date"] < target_date)].copy()
    results = {"target_date": target_date, "history": history}
    for column, (_, _, bounds) in REPORT_METRICS.items():
        valid = history[["date", column]].dropna()
        if len(valid) < 3:
            results[column] = {"point": np.nan, "lower": np.nan, "upper": np.nan, "samples": len(valid)}
            continue
        x = valid["date"].dt.year.to_numpy(dtype=float)
        y = valid[column].to_numpy(dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        target_year = float(target_date.year)
        point = float(intercept + slope * target_year)
        fitted = intercept + slope * x
        residual_error = float(np.sqrt(np.sum((y - fitted) ** 2) / max(1, len(y) - 2)))
        spread = np.sum((x - x.mean()) ** 2)
        prediction_error = residual_error * np.sqrt(
            1 + 1 / len(x) + ((target_year - x.mean()) ** 2 / spread if spread else 0)
        )
        lower, upper = point - 1.96 * prediction_error, point + 1.96 * prediction_error
        minimum, maximum = bounds
        if minimum is not None:
            point, lower, upper = max(minimum, point), max(minimum, lower), max(minimum, upper)
        if maximum is not None:
            point, lower, upper = min(maximum, point), min(maximum, lower), min(maximum, upper)
        results[column] = {"point": point, "lower": lower, "upper": upper, "samples": len(valid)}
    return results


def _resource_modal(county: str):
    return ui.modal(
        ui.div(
            ui.div(
                ui.tags.span("COUNTY RESOURCE INVENTORY", class_="form-step"),
                ui.p(f"Add a mapped resource to the {county} inventory. Coordinates must fall inside the county boundary."),
                class_="resource-form-intro",
            ),
            ui.div(
                ui.input_text("resource_name", "Resource name", placeholder="e.g. Manyatta community borehole"),
                ui.input_select("resource_type", "Resource type", RESOURCE_TYPES),
                class_="resource-form-grid two-column",
            ),
            ui.div(
                ui.input_text("resource_ward", "Ward", placeholder="If known"),
                ui.input_text("resource_village", "Village / settlement", placeholder="If known"),
                class_="resource-form-grid two-column",
            ),
            ui.div(
                ui.input_select("resource_status", "Operating status", RESOURCE_STATUSES),
                ui.input_text("resource_capacity", "Capacity / availability", placeholder="e.g. 20 m³/day or 400 kg seed"),
                class_="resource-form-grid two-column",
            ),
            ui.div(
                ui.input_selectize(
                    "geocode_result",
                    "Find a Kenyan town or settlement",
                    {"": "Start typing a place name", **KENYA_PLACE_CHOICES},
                    selected="",
                    options={"placeholder": "Type a town or settlement name", "maxOptions": 20},
                ),
                ui.div(
                    ui.input_action_button(
                        "use_resource_location",
                        "Use my location",
                        icon=ui.tags.i(class_="bi bi-crosshair"),
                        class_="btn-use-resource-location",
                    ),
                    ui.span("or enter coordinates manually below", class_="location-divider"),
                    class_="location-action-row",
                ),
                ui.div("Choose GPS, town search, or manual coordinates.", class_="resource-location-status", aria_live="polite"),
                ui.p(
                    "Town autocomplete runs locally from the GeoNames Kenya gazetteer. ",
                    ui.tags.a("GeoNames attribution", href="https://www.geonames.org/", target="_blank", rel="noopener noreferrer"),
                    class_="geocoder-disclosure",
                ),
                class_="resource-location-tools",
            ),
            ui.div(
                ui.input_text("resource_latitude", "Latitude", placeholder="e.g. 0.354620"),
                ui.input_text("resource_longitude", "Longitude", placeholder="e.g. 37.582180"),
                class_="resource-form-grid two-column coordinate-entry",
            ),
            ui.input_text_area(
                "resource_notes",
                "Notes",
                placeholder="Ownership, access, maintenance needs or seasonal constraints…",
                rows=4,
            ),
            ui.output_ui("resource_form_message"),
            class_="resource-entry-modal",
        ),
        title=f"Record a resource · {county}",
        size="l",
        easy_close=True,
        footer=ui.div(
            ui.input_action_button(
                "save_resource",
                ui.tags.span("Save resource ", ui.tags.i(class_="bi bi-database-add")),
                class_="btn-save-resource",
            ),
            class_="resource-modal-footer",
        ),
    )


@module.ui
def resource_management_ui():
    latest_months = {
        str(month): calendar.month_name[month]
        for month in sorted(
            AVAILABLE_DATES.loc[AVAILABLE_DATES["date"].dt.year == LATEST_DATE.year, "date"].dt.month.unique()
        )
    }
    return ui.div(
        ui.div(
            ui.div(
                ui.tags.span("COUNTY ACTION REPORT", class_="eyebrow"),
                ui.h1("Plan from conditions to resources"),
                ui.p("Turn monthly grazing indicators into a county brief, then map the assets available for early action."),
                ui.div(
                    ui.span(ui.tags.i(class_="bi bi-file-earmark-bar-graph"), " Data-driven county brief"),
                    ui.span(ui.tags.i(class_="bi bi-database"), " Mapped resource inventory"),
                    class_="hero-chips light-chips",
                ),
            ),
            ui.div(
                ui.input_select("county", "County", AOIS),
                ui.input_select("year", "Year", YEAR_CHOICES, selected=str(LATEST_DATE.year)),
                ui.input_select("month", "Month", latest_months, selected=str(LATEST_DATE.month)),
                class_="county-report-filters",
            ),
            class_="page-hero module-hero resource-hero county-report-hero",
        ),
        loading_frame(ui.output_ui("county_metrics"), "metrics", 116),
        ui.div(
            ui.card(
                ui.card_header(
                    ui.div(ui.span("COUNTY RESOURCE MAP", class_="map-card-kicker"), ui.output_ui("map_title")),
                    ui.div(
                        ui.output_text("resource_count"),
                        ui.input_action_button("open_resource_form", "Record resource", icon=ui.tags.i(class_="bi bi-plus-lg"), class_="btn-record-resource"),
                        class_="resource-map-actions",
                    ),
                ),
                loading_frame(ui.output_ui("resource_map"), "map", 500),
                ui.div(
                    *[
                        ui.span(ui.span(class_="resource-dot", style=f"background:{color}"), label)
                        for label, color in RESOURCE_COLORS.items()
                    ],
                    class_="resource-type-legend",
                ),
                class_="panel-card map-card resource-inventory-map",
            ),
            ui.card(
                ui.card_header(
                    "County planning brief",
                    ui.download_button("download_report", "Download PDF", class_="btn-download-brief"),
                ),
                loading_frame(ui.output_ui("county_brief"), "copy", 500),
                class_="panel-card county-brief-card",
            ),
            class_="county-planning-grid",
        ),
        ui.div(
            ui.card(
                ui.card_header("Selected month vs long-term reference", ui.output_ui("comparison_note")),
                loading_frame(output_widget("comparison_chart"), "chart", 330),
                class_="panel-card chart-card county-report-chart",
            ),
            ui.card(
                ui.card_header("Next-month trend outlook", ui.output_ui("forecast_note")),
                loading_frame(output_widget("forecast_chart"), "chart", 330),
                class_="panel-card chart-card county-report-chart",
            ),
            class_="county-report-charts",
        ),
        ui.card(
            ui.card_header(
                "Registered county resources",
                ui.div(
                    ui.download_button("download_geopackage", "Download GeoPackage", class_="btn-download-gpkg"),
                    class_="register-actions",
                ),
            ),
            loading_frame(ui.output_data_frame("resource_register"), "table", 320),
            class_="panel-card resource-register-card",
        ),
        class_="page-shell county-report-page",
    )


@module.server
def resource_management_server(input, output, session):
    inventory_revision = reactive.value(0)
    form_message = reactive.value("")

    @reactive.effect
    @reactive.event(input.year)
    def _sync_months():
        months = sorted(
            AVAILABLE_DATES.loc[AVAILABLE_DATES["date"].dt.year == int(input.year()), "date"].dt.month.unique()
        )
        current = int(input.month()) if input.month() else max(months)
        selected = current if current in months else max(months)
        ui.update_select(
            "month",
            choices={str(month): calendar.month_name[month] for month in months},
            selected=str(selected),
            session=session,
        )

    @reactive.calc
    def selected_date():
        year = int(input.year())
        valid_months = sorted(
            AVAILABLE_DATES.loc[AVAILABLE_DATES["date"].dt.year == year, "date"].dt.month.unique()
        )
        requested = int(input.month()) if input.month() else max(valid_months)
        month = requested if requested in valid_months else max(valid_months)
        return pd.Timestamp(year=year, month=month, day=1)

    @reactive.calc
    def selected_frame():
        county = AOIS[input.county()]
        data = climate_data()
        return data[(data["ADM1_EN"] == county) & (data["date"] == selected_date())].copy()

    @reactive.calc
    def county_summary():
        frame = selected_frame()
        metrics = {column: _weighted(frame, column) for column in ["GCI", "NDVI", "prcp", "lst", "msdi"]}
        monthly_series = _county_monthly_series(AOIS[input.county()])
        baseline = monthly_series[monthly_series["date"].dt.month == selected_date().month][list(REPORT_METRICS)].mean().to_dict()
        classes = frame["GCI_class"].value_counts().to_dict()
        bad_wards = frame[frame["GCI_class"].isin(["Very poor", "Poor"])].sort_values("GCI")[["ADM3_EN", "GCI", "GCI_class"]].to_dict("records")
        good_wards = frame[frame["GCI_class"].isin(["Good", "Very good"])].sort_values("GCI", ascending=False)[["ADM3_EN", "GCI", "GCI_class"]].to_dict("records")
        return {
            "metrics": metrics, "baseline": baseline, "classes": classes,
            "wards": int(frame["ADM3_EN"].nunique()), "bad_wards": bad_wards, "good_wards": good_wards,
        }

    @reactive.calc
    def forecast():
        return _next_month_forecast(AOIS[input.county()], selected_date())

    @reactive.calc
    def county_resources():
        inventory_revision()
        return list_resources(AOIS[input.county()])

    @render.ui
    def county_metrics():
        summary = county_summary()
        metrics = summary["metrics"]
        baseline = summary["baseline"]
        def reference(column: str, decimals: int, unit: str = "") -> str:
            lta = baseline.get(column, np.nan)
            delta = metrics[column] - lta
            if not np.isfinite(lta) or not np.isfinite(delta):
                return "Long-term reference unavailable"
            suffix = f" {unit}" if unit else ""
            return f"LTA {lta:.{decimals}f}{suffix} · {delta:+.{decimals}f}{suffix}"
        cards = [
            ("Grazing condition", f"{metrics['GCI']:.1f}" if np.isfinite(metrics["GCI"]) else "NA", reference("GCI", 1)),
            ("NDVI", f"{metrics['NDVI']:.3f}" if np.isfinite(metrics["NDVI"]) else "NA", reference("NDVI", 3)),
            ("Rainfall", f"{metrics['prcp']:.1f} mm" if np.isfinite(metrics["prcp"]) else "NA", reference("prcp", 1, "mm")),
            ("Land temperature", f"{metrics['lst']:.1f} °C" if np.isfinite(metrics["lst"]) else "NA", reference("lst", 1, "°C")),
            ("MSDI", f"{metrics['msdi']:.3f}" if np.isfinite(metrics["msdi"]) else "NA", reference("msdi", 3)),
        ]
        return ui.div(
            *[
                ui.div(ui.span(label), ui.strong(value), ui.tags.small(note), class_="county-metric-card")
                for label, value, note in cards
            ],
            class_="county-metric-strip",
        )

    @render.ui
    def map_title():
        return ui.span(f"{AOIS[input.county()]} · available assets", class_="resource-map-title")

    @render.text
    def resource_count():
        count = len(county_resources())
        return f"{count} mapped resource{'s' if count != 1 else ''}"

    @render.ui
    def resource_map():
        points = []
        for row in county_resources().itertuples():
            place = " · ".join(part for part in [row.village, row.ward, row.county] if part)
            points.append(
                {
                    "name": row.name,
                    "type": row.resource_type,
                    "lat": row.geometry.y,
                    "lon": row.geometry.x,
                    "color": RESOURCE_COLORS.get(row.resource_type, "#667873"),
                    "size": 19,
                    "popup": (
                        f"<strong>{escape(row.name)}</strong><span>{escape(row.resource_type)}</span><hr>"
                        f"<span>{escape(place)}</span><span>Status <b>{escape(row.status)}</b></span>"
                        f"<span>Capacity <b>{escape(row.capacity or 'Not recorded')}</b></span>"
                    ),
                }
            )
        return map_container(
            points,
            height=500,
            label=f"Mapped resources in {AOIS[input.county()]}",
            geojson=county_boundary_geojson(AOIS[input.county()]),
            fit_geojson=True,
        )

    @render.ui
    def comparison_note():
        return ui.span(selected_date().strftime("%B %Y · LTA uses all available years"), class_="header-note")

    @render_widget
    def comparison_chart():
        summary = county_summary()
        current = summary["metrics"]
        baseline = summary["baseline"]
        columns = list(REPORT_METRICS)
        labels = [REPORT_METRICS[column][0] for column in columns]
        ratios = [100 * current[column] / baseline[column] if baseline.get(column) not in (0, None) and np.isfinite(baseline[column]) else np.nan for column in columns]
        current_text = [
            f"{current[column]:.3f} {REPORT_METRICS[column][1]}".strip()
            if np.isfinite(current[column]) else "NA"
            for column in columns
        ]
        baseline_text = [
            f"{baseline[column]:.3f} {REPORT_METRICS[column][1]}".strip()
            if np.isfinite(baseline.get(column, np.nan)) else "NA"
            for column in columns
        ]
        figure = go.Figure()
        figure.add_bar(
            x=labels, y=[100] * len(labels), name="Long-term monthly reference",
            marker_color="#b8c5c0", customdata=baseline_text,
            hovertemplate="%{x}<br>LTA: %{customdata}<extra></extra>",
        )
        figure.add_bar(
            x=labels, y=ratios, name="Selected month", marker_color="#27866f",
            customdata=current_text, hovertemplate="%{x}<br>Selected: %{customdata}<br>%{y:.1f}% of LTA<extra></extra>",
        )
        figure.update_layout(
            barmode="group", height=330, margin={"l": 52, "r": 18, "t": 18, "b": 52},
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font={"family": "DM Sans", "color": "#52635f"},
            yaxis={"title": "Monthly LTA = 100", "gridcolor": "#e4ebe7", "zeroline": False},
            legend={"orientation": "h", "y": 1.12, "x": 0}, hovermode="x unified",
        )
        return figure

    @render.ui
    def forecast_note():
        return ui.span(
            f"{forecast()['target_date']:%B %Y} · 95% trend ranges",
            class_="header-note",
        )

    @render_widget
    def forecast_chart():
        outlook = forecast()
        history = outlook["history"]
        columns = list(REPORT_METRICS)
        figure = make_subplots(rows=1, cols=5, subplot_titles=[REPORT_METRICS[column][0] for column in columns])
        for index, column in enumerate(columns, start=1):
            valid = history[["date", column]].dropna()
            result = outlook[column]
            figure.add_trace(
                go.Scatter(
                    x=valid["date"].dt.year, y=valid[column], mode="lines+markers",
                    line={"color": "#8ba09a", "width": 1.5}, marker={"size": 5},
                    name="Historical target month", legendgroup="history", showlegend=index == 1,
                    hovertemplate="%{x}: %{y:.3f}<extra></extra>",
                ),
                row=1, col=index,
            )
            if np.isfinite(result["point"]):
                figure.add_trace(
                    go.Scatter(
                        x=[outlook["target_date"].year], y=[result["point"]], mode="markers",
                        marker={"color": "#f0b541", "size": 10, "symbol": "diamond"},
                        error_y={
                            "type": "data", "symmetric": False,
                            "array": [result["upper"] - result["point"]],
                            "arrayminus": [result["point"] - result["lower"]],
                            "color": "#d18d20", "thickness": 2, "width": 4,
                        },
                        customdata=[[result["lower"], result["upper"]]],
                        name="Next-month forecast", legendgroup="forecast", showlegend=index == 1,
                        hovertemplate="Forecast %{y:.3f}<br>95% range %{customdata[0]:.3f}–%{customdata[1]:.3f}<extra></extra>",
                    ),
                    row=1, col=index,
                )
            figure.update_xaxes(tickformat="d", showgrid=False, row=1, col=index)
            figure.update_yaxes(gridcolor="#e5ebe7", zeroline=False, row=1, col=index)
        figure.update_layout(
            height=330, margin={"l": 35, "r": 15, "t": 52, "b": 42},
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font={"family": "DM Sans", "color": "#52635f", "size": 10},
            legend={"orientation": "h", "y": 1.22, "x": 0}, hovermode="x unified",
        )
        return figure

    @render.ui
    def county_brief():
        summary = county_summary()
        metrics = summary["metrics"]
        baseline = summary["baseline"]
        outlook = forecast()
        priority = int(summary["classes"].get("Very poor", 0) + summary["classes"].get("Poor", 0))
        resource_total = len(county_resources())
        actions = _planning_actions(summary, resource_total)
        bad_chips = [
            ui.span(f"{ward['ADM3_EN']} · {ward['GCI']:.1f}", class_="ward-chip bad")
            for ward in summary["bad_wards"]
        ] or [ui.span("None in this month", class_="empty-ward-note")]
        good_chips = [
            ui.span(f"{ward['ADM3_EN']} · {ward['GCI']:.1f}", class_="ward-chip good")
            for ward in summary["good_wards"]
        ] or [ui.span("None in this month", class_="empty-ward-note")]

        return ui.div(
            ui.div(
                ui.span(selected_date().strftime("%B %Y"), class_="brief-period"),
                ui.span(_condition(metrics["GCI"]), class_=f"brief-condition condition-{_condition(metrics['GCI']).lower().replace(' ', '-')}")
            ),
            ui.h2(f"{AOIS[input.county()]} grazing and resource brief"),
            ui.p(
                f"The county mean GCI is {metrics['GCI']:.1f}, classified as {_condition(metrics['GCI']).lower()}. "
                f"The assessment covers {summary['wards']} wards; {priority} {'is' if priority == 1 else 'are'} currently poor or very poor.",
                class_="brief-lead",
            ),
            ui.div(
                *[
                    ui.div(
                        ui.span(REPORT_METRICS[column][0]),
                        ui.strong(f"{metrics[column]:.3f}" if column in ("NDVI", "msdi") else f"{metrics[column]:.1f}"),
                        ui.tags.small(
                            f"LTA {baseline[column]:.3f} · {metrics[column] - baseline[column]:+.3f}"
                            if column in ("NDVI", "msdi")
                            else f"LTA {baseline[column]:.1f} · {metrics[column] - baseline[column]:+.1f}"
                        ),
                    )
                    for column in REPORT_METRICS
                ],
                class_="indicator-reference-list",
            ),
            ui.div(
                ui.div(
                    ui.span("PRIORITY WARDS", class_="ward-list-kicker bad"),
                    ui.h3("Poor / very poor"),
                    ui.div(*bad_chips, class_="ward-chip-list"),
                ),
                ui.div(
                    ui.span("STRONGER WARDS", class_="ward-list-kicker good"),
                    ui.h3("Good / very good"),
                    ui.div(*good_chips, class_="ward-chip-list"),
                ),
                class_="ward-signal-grid",
            ),
            ui.div(
                ui.div(
                    ui.span("NEXT-MONTH OUTLOOK", class_="forecast-kicker"),
                    ui.h3(outlook["target_date"].strftime("Trend estimate for %B %Y")),
                ),
                ui.div(
                    *[
                        ui.div(
                            ui.span(REPORT_METRICS[column][0]),
                            ui.strong(
                                f"{outlook[column]['point']:.3f}" if column in ("NDVI", "msdi") and np.isfinite(outlook[column]["point"])
                                else f"{outlook[column]['point']:.1f}" if np.isfinite(outlook[column]["point"])
                                else "NA"
                            ),
                            ui.tags.small(
                                f"95% range {outlook[column]['lower']:.3f}–{outlook[column]['upper']:.3f}"
                                if column in ("NDVI", "msdi") and np.isfinite(outlook[column]["lower"])
                                else f"95% range {outlook[column]['lower']:.1f}–{outlook[column]['upper']:.1f}"
                                if np.isfinite(outlook[column]["lower"])
                                else "Insufficient history"
                            ),
                        )
                        for column in REPORT_METRICS
                    ],
                    class_="forecast-value-grid",
                ),
                ui.p("Ranges come from a linear trend fitted only to prior observations for the forecast month; they express statistical uncertainty, not a weather forecast.", class_="forecast-method"),
                class_="brief-forecast-panel",
            ),
            ui.h3("Recommended planning checks"),
            ui.tags.ol(*[ui.tags.li(action) for action in actions], class_="brief-action-list"),
            ui.div(
                ui.tags.i(class_="bi bi-info-circle"),
                "This report is a screening brief. Confirm resource access, ownership, condition and local authority guidance before deployment.",
                class_="brief-caveat",
            ),
            class_="county-brief",
        )

    @reactive.effect
    @reactive.event(input.open_resource_form)
    def _show_resource_form():
        form_message.set("")
        ui.modal_show(_resource_modal(AOIS[input.county()]))

    @reactive.effect
    @reactive.event(input.geocode_result)
    def _apply_geocode_result():
        selected = input.geocode_result()
        if not selected:
            return
        result = get_kenya_place(selected)
        if not result:
            return
        ui.update_text("resource_latitude", value=f"{result['latitude']:.6f}", session=session)
        ui.update_text("resource_longitude", value=f"{result['longitude']:.6f}", session=session)

    @reactive.effect
    @reactive.event(input.save_resource)
    def _save_resource():
        name = input.resource_name().strip()
        if not name:
            form_message.set("Enter a resource name before saving.")
            return
        try:
            latitude = float(input.resource_latitude().strip())
            longitude = float(input.resource_longitude().strip())
        except ValueError:
            form_message.set("Enter valid numeric latitude and longitude coordinates.")
            return
        try:
            resource_id = save_resource(
                name=name,
                resource_type=input.resource_type(),
                county=AOIS[input.county()],
                ward=input.resource_ward().strip(),
                village=input.resource_village().strip(),
                status=input.resource_status(),
                capacity=input.resource_capacity().strip(),
                notes=input.resource_notes().strip(),
                latitude=latitude,
                longitude=longitude,
            )
        except ValueError as exc:
            form_message.set(str(exc))
            return
        inventory_revision.set(inventory_revision() + 1)
        ui.modal_remove()
        ui.notification_show(f"Resource {resource_id[:8]} saved successfully.", type="message", duration=6)

    @render.ui
    def resource_form_message():
        return ui.p(form_message(), class_="resource-form-message") if form_message() else None

    @render.data_frame
    def resource_register():
        frame = county_resources().copy()
        if frame.empty:
            frame = pd.DataFrame(columns=["Name", "Type", "Ward", "Village", "Status", "Capacity", "Latitude", "Longitude", "Recorded"])
        else:
            frame["Latitude"] = frame.geometry.y.round(6)
            frame["Longitude"] = frame.geometry.x.round(6)
            frame = frame.rename(
                columns={
                    "name": "Name", "resource_type": "Type", "ward": "Ward", "village": "Village",
                    "status": "Status", "capacity": "Capacity", "recorded_at": "Recorded",
                }
            )[["Name", "Type", "Ward", "Village", "Status", "Capacity", "Latitude", "Longitude", "Recorded"]]
        return render.DataGrid(frame, height="320px", width="100%", filters=True)

    @render.download(
        filename=lambda: f"{AOIS[input.county()].lower().replace(' ', '_')}_{selected_date():%Y_%m}_county_report.pdf",
        media_type="application/pdf",
    )
    def download_report():
        summary = county_summary()
        outlook = forecast()
        yield build_county_report_pdf(
            county=AOIS[input.county()],
            selected_date=selected_date(),
            condition=_condition(summary["metrics"]["GCI"]),
            summary=summary,
            outlook=outlook,
            metric_labels={column: details[0] for column, details in REPORT_METRICS.items()},
            actions=_planning_actions(summary, len(county_resources())),
        )

    @render.download(filename="resources.gpkg", media_type="application/geopackage+sqlite3")
    def download_geopackage():
        return str(GEOPACKAGE_PATH)
