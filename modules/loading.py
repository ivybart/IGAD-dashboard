"""Stable loading frames used by Shiny outputs across dashboard modules."""

from shiny import ui


def loading_frame(content, kind="panel", height=None):
    """Keep output geometry present and display an animated skeleton until ready."""
    style = f"min-height:{height}px" if height else None
    return ui.div(
        content,
        ui.div(
            ui.span(class_="skeleton-line skeleton-line-wide"),
            ui.span(class_="skeleton-line skeleton-line-mid"),
            ui.span(class_="skeleton-line skeleton-line-short"),
            class_="skeleton-layer",
            aria_hidden="true",
        ),
        class_=f"loading-frame skeleton-{kind}",
        style=style,
        aria_live="polite",
    )
