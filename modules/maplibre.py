"""Helpers for rendering MapLibre maps through a lightweight JS component."""

import json
import math
from collections.abc import Mapping
from datetime import date, datetime

from shiny import ui


def _json_safe(value):
    """Convert pandas/NumPy values into strict JSON-compatible Python values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return _json_safe(value.item())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def map_container(points, *, center=(40.0, 1.0), zoom=4.3, height=390, label="Interactive map", raster_tiles=None, raster_bounds=None, raster_minzoom=4, raster_maxzoom=14, geojson=None, show_controls=True, locked=False, fit_geojson=False):
    """Return a MapLibre host element with serialized GeoJSON-like marker data."""
    records = points.to_dict(orient="records") if hasattr(points, "to_dict") else points
    records = _json_safe(records)
    return ui.div(
        class_="maplibre-map",
        role="region",
        aria_label=label,
        data_points=json.dumps(records, allow_nan=False),
        data_center=json.dumps(list(center)),
        data_zoom=str(zoom),
        data_raster_tiles=raster_tiles or "",
        data_raster_bounds=json.dumps(list(raster_bounds)) if raster_bounds else "",
        data_raster_minzoom=str(raster_minzoom),
        data_raster_maxzoom=str(raster_maxzoom),
        data_geojson=json.dumps(_json_safe(geojson), allow_nan=False) if geojson else "",
        data_show_controls="true" if show_controls else "false",
        data_locked="true" if locked else "false",
        data_fit_geojson="true" if fit_geojson else "false",
        style=f"height:{height}px",
    )
