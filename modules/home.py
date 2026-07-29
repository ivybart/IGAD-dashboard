from shiny import module, render, ui

from services.grassland_health import STATUS_COLORS, county_health_geojson, ward_health
from .maplibre import map_container


@module.ui
def home_ui():
    return ui.div(
        ui.div(
            ui.output_ui("regional_map"),
            ui.div(
                ui.div(ui.span("LIVE", class_="live-badge"), ui.span("REGIONAL OPERATIONS PICTURE", class_="map-kicker"), class_="map-meta"),
                ui.h1("Monitoring grasslands", ui.tags.br(), ui.span("in the ASAL regions.")),
                ui.p("Use earth observation to understand grazing conditions and compare ward-level changes across the ASAL region."),
                ui.div(ui.output_ui("latest_period"), class_="hero-chips"),
                class_="map-headline",
            ),
            ui.div(*[
                ui.span(ui.span(class_="health-dot", style=f"background:{color}"), label)
                for label, color in STATUS_COLORS.items()
            ], class_="map-legend grassland-legend"),
            class_="immersive-map",
        ),
        ui.div(
            ui.div(
                ui.div(ui.span("01", class_="intel-index"), ui.div(ui.span("AREAS MONITORED", class_="intel-label"), ui.strong("3"), ui.span("ASAL counties")), class_="intel-stat"),
                ui.div(ui.span("02", class_="intel-index"), ui.div(ui.span("POOR / VERY POOR", class_="intel-label"), ui.strong("10 wards"), ui.span("Priority grazing-condition screen")), class_="intel-stat critical"),
                ui.div(ui.span("03", class_="intel-index"), ui.div(ui.span("GOOD / VERY GOOD", class_="intel-label"), ui.strong("12 wards"), ui.span("Potential alternatives to assess")), class_="intel-stat"),
                class_="overview-intelligence",
                style="background:linear-gradient(135deg,#0b3935,#123f3a)",
            ),
            class_="overview-intelligence-wrap",
        ),
        ui.div(ui.div(ui.tags.span("GRASSLAND EVIDENCE", class_="eyebrow"), ui.h2("From regional picture to ward intelligence")), ui.p("Combine vegetation, rainfall, heat and surface-variability indicators into an actionable view of grazing conditions."), class_="section-heading"),
        ui.div(
            ui.tags.a(
                ui.div(ui.tags.i(class_="bi bi-activity"), class_="teaser-icon"),
                ui.span("GRASSLAND INTELLIGENCE", class_="teaser-kicker"),
                ui.h3("Monitor grazing condition"),
                ui.p("Map GCI classes alongside NDVI, rainfall and heat to identify poor wards and stronger alternatives."),
                ui.span("Explore grasslands  →", class_="teaser-link"),
                href="#",
                aria_label="Open Grassland health",
                onclick="event.preventDefault(); document.querySelector('[data-value=\"Grassland health\"]')?.click();",
                class_="module-teaser module-teaser-link drought-teaser",
            ),
            ui.tags.a(
                ui.div(ui.tags.i(class_="bi bi-pin-map"), class_="teaser-icon"),
                ui.span("COUNTY ACTION PLANNING", class_="teaser-kicker"),
                ui.h3("Connect conditions to resources"),
                ui.p("Create a county brief and map boreholes, seed banks, nurseries and livestock watering points."),
                ui.span("Open county planning  →", class_="teaser-link"),
                href="#",
                aria_label="Open County planning",
                onclick="event.preventDefault(); document.querySelector('[data-value=\"County planning\"]')?.click();",
                class_="module-teaser module-teaser-link resource-teaser",
            ),
            class_="module-teasers reduced-modules",
        ),
        class_="page-shell",
    )


@module.server
def home_server(input, output, session):
    @render.ui
    def latest_period():
        latest = ward_health()["date"].max()
        return ui.span(latest.strftime("Updated %B %Y"))

    @render.ui
    def regional_map():
        geojson = county_health_geojson()
        return map_container(
            [], height=650, label="Latest county grassland health map", geojson=geojson,
            show_controls=False, locked=True, fit_geojson=True,
        )
