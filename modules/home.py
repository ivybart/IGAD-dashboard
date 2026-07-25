from shiny import module, render, ui

from services.gee_climate import indicator_geojson
from .maplibre import map_container


@module.ui
def home_ui():
    return ui.div(
        ui.div(
            ui.output_ui("regional_map"),
            ui.div(
                ui.div(ui.span("LIVE", class_="live-badge"), ui.span("REGIONAL OPERATIONS PICTURE", class_="map-kicker"), class_="map-meta"),
                ui.h1("See the pressure.", ui.tags.br(), ui.span("Move before crisis.")),
                ui.p("One shared view of climate stress, field capacity, and local signals across Kenya's Twende landscapes."),
                ui.div(ui.span("Updated April 2026"), ui.span("11 monitored counties"), class_="hero-chips"),
                class_="map-headline",
            ),
            ui.div(ui.span(class_="legend-dot warning"), "Lower CDI-3", ui.span(class_="legend-dot watch"), "Mid-range", ui.span(class_="legend-dot normal"), "Higher CDI-3", class_="map-legend"),
            class_="immersive-map",
        ),
        ui.div(
            ui.div(
                ui.div(ui.span("01", class_="intel-index"), ui.div(ui.span("AREAS MONITORED", class_="intel-label"), ui.strong("11"), ui.span("Twende counties")), class_="intel-stat"),
                ui.div(ui.span("02", class_="intel-index"), ui.div(ui.span("ACTIVE ALERT", class_="intel-label"), ui.strong("4 counties"), ui.span("Latest CDI-3 classification")), class_="intel-stat critical"),
                ui.div(ui.span("03", class_="intel-index"), ui.div(ui.span("WARD COVERAGE", class_="intel-label"), ui.strong("262"), ui.span("Climate observation series")), class_="intel-stat"),
                class_="overview-intelligence",
                style="background:linear-gradient(135deg,#0b3935,#123f3a)",
            ),
            class_="overview-intelligence-wrap",
        ),
        ui.div(ui.div(ui.tags.span("MISSION CONTROL", class_="eyebrow"), ui.h2("From signal to coordinated action")), ui.p("Move from regional context into the workflow that needs attention."), class_="section-heading"),
        ui.div(
            ui.div(ui.div(ui.tags.i(class_="bi bi-activity"), class_="teaser-icon"), ui.span("CLIMATE INTELLIGENCE", class_="teaser-kicker"), ui.h3("Monitor drought"), ui.p("Read satellite signals, compare trajectories, and turn sustained stress into an action brief."), ui.span("Explore monitor  →", class_="teaser-link"), class_="module-teaser drought-teaser"),
            ui.div(ui.div(ui.tags.i(class_="bi bi-droplet-half"), class_="teaser-icon"), ui.span("FIELD CAPACITY", class_="teaser-kicker"), ui.h3("Coordinate resources"), ui.p("See operational assets, capacity gaps, and the facilities that require intervention first."), ui.span("View readiness  →", class_="teaser-link"), class_="module-teaser resource-teaser"),
            ui.div(ui.div(ui.tags.i(class_="bi bi-broadcast-pin"), class_="teaser-icon"), ui.span("COMMUNITY SIGNALS", class_="teaser-kicker"), ui.h3("Listen locally"), ui.p("Bring verified community observations into the same decision-making picture."), ui.span("Open reports  →", class_="teaser-link"), class_="module-teaser citizen-teaser"),
            class_="module-teasers",
        ),
        class_="page-shell",
    )


@module.server
def home_server(input, output, session):
    @render.ui
    def regional_map():
        geojson, _ = indicator_geojson("cdi3")
        return map_container(
            [], height=650, label="Latest county CDI-3 drought map", geojson=geojson,
            show_controls=False, locked=True, fit_geojson=True,
        )
