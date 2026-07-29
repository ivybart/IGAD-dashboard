"""GeoPackage-backed county resource inventory."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, shape

from .gee_climate import BOUNDARIES_PATH


GEOPACKAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "resources.gpkg"
LAYER_NAME = "resources"
RESOURCE_TYPES = ["Grass seed bank", "Borehole", "Nursery", "Animal watering point"]
RESOURCE_STATUSES = ["Operational", "Needs maintenance", "Seasonal", "Planned", "Out of service"]
_WRITE_LOCK = Lock()


def _empty_inventory() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "resource_id": pd.Series(dtype="str"),
            "name": pd.Series(dtype="str"),
            "resource_type": pd.Series(dtype="str"),
            "county": pd.Series(dtype="str"),
            "ward": pd.Series(dtype="str"),
            "village": pd.Series(dtype="str"),
            "status": pd.Series(dtype="str"),
            "capacity": pd.Series(dtype="str"),
            "notes": pd.Series(dtype="str"),
            "recorded_at": pd.Series(dtype="str"),
            "geometry": gpd.GeoSeries([], crs="EPSG:4326"),
        },
        geometry="geometry",
        crs="EPSG:4326",
    )


def initialize_inventory(path: Path = GEOPACKAGE_PATH) -> None:
    """Create an empty, valid GeoPackage resource layer when none exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    with _WRITE_LOCK:
        if not path.exists():
            _empty_inventory().to_file(path, layer=LAYER_NAME, driver="GPKG", engine="pyogrio")


def list_resources(county: str | None = None, path: Path = GEOPACKAGE_PATH) -> gpd.GeoDataFrame:
    """Read all resources, optionally filtered to one county."""
    initialize_inventory(path)
    inventory = gpd.read_file(path, layer=LAYER_NAME, engine="pyogrio")
    if county:
        inventory = inventory[inventory["county"] == county]
    return inventory.reset_index(drop=True)


def save_resource(
    *,
    name: str,
    resource_type: str,
    county: str,
    ward: str,
    village: str,
    status: str,
    capacity: str,
    notes: str,
    latitude: float,
    longitude: float,
    path: Path = GEOPACKAGE_PATH,
) -> str:
    """Append one point resource to the GeoPackage and return its identifier."""
    if resource_type not in RESOURCE_TYPES:
        raise ValueError("Unsupported resource type")
    if status not in RESOURCE_STATUSES:
        raise ValueError("Unsupported resource status")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Coordinates are outside the valid latitude/longitude range")
    if not point_is_in_county(county, latitude, longitude):
        raise ValueError(f"The coordinates fall outside {county} County")

    initialize_inventory(path)
    resource_id = uuid4().hex
    record = gpd.GeoDataFrame(
        [
            {
                "resource_id": resource_id,
                "name": name,
                "resource_type": resource_type,
                "county": county,
                "ward": ward,
                "village": village,
                "status": status,
                "capacity": capacity,
                "notes": notes,
                "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "geometry": Point(longitude, latitude),
            }
        ],
        geometry="geometry",
        crs="EPSG:4326",
    )
    with _WRITE_LOCK:
        record.to_file(path, layer=LAYER_NAME, driver="GPKG", engine="pyogrio", mode="a")
    return resource_id


def county_boundary_geojson(county: str) -> dict:
    """Return a single styled county feature for the resource map."""
    boundaries = json.loads(BOUNDARIES_PATH.read_text())
    matches = [
        feature
        for feature in boundaries["features"]
        if feature["properties"]["ADM1_EN"].strip() == county
    ]
    if not matches:
        raise ValueError(f"No county boundary is available for {county}")
    feature = matches[0]
    feature["properties"].update(
        {
            "fill_color": "#2d7f6e",
            "indicator": "Resource planning area",
            "display_value": county,
            "landscape": "County resource inventory",
        }
    )
    return {"type": "FeatureCollection", "features": [feature]}


def point_is_in_county(county: str, latitude: float, longitude: float) -> bool:
    boundary = county_boundary_geojson(county)["features"][0]
    return bool(shape(boundary["geometry"]).covers(Point(longitude, latitude)))


initialize_inventory()
