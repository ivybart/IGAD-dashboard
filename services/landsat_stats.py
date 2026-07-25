"""On-demand Landsat statistics from STAC-hosted Cloud Optimized GeoTIFFs."""

from __future__ import annotations

import calendar
import json
import os
import warnings
from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import planetary_computer
import rasterio
from planetary_computer import sign_inplace
from pystac_client import Client
from rasterio.errors import WindowError
from rasterio.features import geometry_mask, geometry_window
from rasterio.enums import Resampling
from affine import Affine
from rasterio.warp import transform_geom
from rasterio.warp import calculate_default_transform, reproject, transform_bounds
from rasterio.transform import from_bounds
from rasterio.vrt import WarpedVRT


STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "landsat-c2-l2"
BOUNDARIES = Path(__file__).parents[1] / "data" / "Kenya_adm1_twende.geojson"
DERIVED_DIR = Path(__file__).parents[1] / "outputs" / "live_ndvi"
SR_SCALE = 0.0000275
SR_OFFSET = -0.2


class LandsatDataError(RuntimeError):
    """A user-displayable failure while retrieving live Landsat statistics."""


@lru_cache(maxsize=1)
def _county_features() -> dict[str, dict]:
    contents = json.loads(BOUNDARIES.read_text())
    return {feature["properties"]["ADM1_EN"]: feature for feature in contents["features"]}


def available_counties() -> dict[str, str]:
    return {name.lower().replace(" ", "_"): name for name in sorted(_county_features())}


def get_county_feature(county_key: str) -> dict:
    counties = available_counties()
    if county_key not in counties:
        raise LandsatDataError(f"Unknown Twende county: {county_key}")
    return _county_features()[counties[county_key]]


def _asset(item, common_name: str):
    aliases = {"red": ("red", "SR_B4"), "nir08": ("nir08", "nir", "SR_B5")}
    for key in aliases[common_name]:
        if key in item.assets:
            return item.assets[key]
    for asset in item.assets.values():
        bands = asset.extra_fields.get("eo:bands", []) + asset.extra_fields.get("raster:bands", [])
        if any(band.get("common_name") == common_name for band in bands):
            return asset
    raise LandsatDataError(f"Landsat item {item.id} has no {common_name} surface-reflectance asset.")


def _qa_asset(item):
    for key in ("qa_pixel", "QA_PIXEL"):
        if key in item.assets:
            return item.assets[key]
    raise LandsatDataError(f"Landsat item {item.id} has no QA_PIXEL asset.")


def _clear_pixel_mask(qa: np.ndarray) -> np.ndarray:
    """USGS QA_PIXEL filter: fill, dilated cloud, cirrus, cloud, shadow, snow."""
    qa_values = np.asarray(np.ma.filled(qa, 1), dtype="uint16")
    unwanted_bits = sum(1 << bit for bit in (0, 1, 2, 3, 4, 5))
    return (qa_values & unwanted_bits) == 0


def _scene_ndvi_stats(item, geometry_wgs84: dict) -> tuple[float, int] | None:
    red_url = planetary_computer.sign(_asset(item, "red").href)
    nir_url = planetary_computer.sign(_asset(item, "nir08").href)
    qa_url = planetary_computer.sign(_qa_asset(item).href)
    env = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF,.tiff",
        "GDAL_HTTP_MULTIRANGE": "YES",
        "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    }
    with rasterio.Env(**env), rasterio.open(red_url) as red_src:
        geometry = transform_geom("EPSG:4326", red_src.crs, geometry_wgs84)
        try:
            window = geometry_window(red_src, [geometry])
        except WindowError:
            return None
        scale = max(1.0, max(window.width, window.height) / 768.0)
        out_height = max(1, round(window.height / scale))
        out_width = max(1, round(window.width / scale))
        out_shape = (out_height, out_width)
        red = red_src.read(1, window=window, out_shape=out_shape, masked=True, resampling=Resampling.average).astype("float32")
        transform = red_src.window_transform(window) * Affine.scale(window.width / out_width, window.height / out_height)
        with rasterio.open(nir_url) as nir_src:
            nir = nir_src.read(1, window=window, out_shape=out_shape, masked=True, resampling=Resampling.average).astype("float32")
        with rasterio.open(qa_url) as qa_src:
            qa = qa_src.read(1, window=window, out_shape=out_shape, masked=True, resampling=Resampling.nearest)
    inside = geometry_mask([geometry], out_shape=red.shape, transform=transform, invert=True)
    red = red * SR_SCALE + SR_OFFSET
    nir = nir * SR_SCALE + SR_OFFSET
    denominator = nir + red
    valid = inside & _clear_pixel_mask(qa) & ~np.ma.getmaskarray(red) & ~np.ma.getmaskarray(nir) & (np.abs(denominator) > 1e-6)
    ndvi = np.full(red.shape, np.nan, dtype="float32")
    ndvi[valid] = (nir[valid] - red[valid]) / denominator[valid]
    valid_values = ndvi[np.isfinite(ndvi) & (ndvi >= -1) & (ndvi <= 1)]
    if valid_values.size == 0:
        return None
    return float(valid_values.mean()), int(valid_values.size)


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"


def _latest_complete_month() -> pd.Timestamp:
    return pd.Timestamp(date.today().replace(day=1)) - pd.DateOffset(months=1)


@lru_cache(maxsize=32)
def build_latest_median_ndvi_cog(county_key: str) -> tuple[Path, dict]:
    """Stream Landsat COG windows and write a derived latest-month median NDVI COG."""
    feature = get_county_feature(county_key)
    county_name = feature["properties"]["ADM1_EN"]
    month = _latest_complete_month()
    start, end = _month_bounds(month.year, month.month)
    safe_name = county_key.replace("/", "_")
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    output = DERIVED_DIR / f"{safe_name}_{month:%Y_%m}_median_ndvi_qa_v2.tif"
    metadata_path = output.with_suffix(".json")
    if output.exists() and metadata_path.exists():
        return output.resolve(), json.loads(metadata_path.read_text())

    catalog = Client.open(STAC_URL, modifier=sign_inplace)
    items = sorted(
        catalog.search(collections=[COLLECTION], intersects=feature["geometry"], datetime=f"{start}/{end}", query={"eo:cloud_cover": {"lt": 45}}, max_items=8).items(),
        key=lambda item: item.properties.get("eo:cloud_cover", 100),
    )[:3]
    if not items:
        raise LandsatDataError(f"No Landsat scenes were found for {county_name} in {month:%B %Y}.")

    coordinates = feature["geometry"]["coordinates"]
    flat = [point for ring in coordinates for point in ring] if feature["geometry"]["type"] == "Polygon" else [point for polygon in coordinates for ring in polygon for point in ring]
    west, south = min(p[0] for p in flat), min(p[1] for p in flat)
    east, north = max(p[0] for p in flat), max(p[1] for p in flat)
    target_bounds = transform_bounds("EPSG:4326", "EPSG:3857", west, south, east, north)
    resolution = 120.0
    width = max(1, round((target_bounds[2] - target_bounds[0]) / resolution))
    height = max(1, round((target_bounds[3] - target_bounds[1]) / resolution))
    target_transform = from_bounds(*target_bounds, width, height)
    target_geometry = transform_geom("EPSG:4326", "EPSG:3857", feature["geometry"])
    inside = geometry_mask([target_geometry], out_shape=(height, width), transform=target_transform, invert=True)
    env = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF,.tiff", "GDAL_HTTP_MULTIRANGE": "YES"}
    scenes = []
    scene_ids = []
    with rasterio.Env(**env):
        for item in items:
            try:
                red_url = planetary_computer.sign(_asset(item, "red").href)
                nir_url = planetary_computer.sign(_asset(item, "nir08").href)
                qa_url = planetary_computer.sign(_qa_asset(item).href)
                vrt_options = {"crs": "EPSG:3857", "transform": target_transform, "width": width, "height": height, "resampling": Resampling.bilinear}
                with rasterio.open(red_url) as red_src, WarpedVRT(red_src, **vrt_options) as red_vrt:
                    red = red_vrt.read(1, masked=True).astype("float32") * SR_SCALE + SR_OFFSET
                with rasterio.open(nir_url) as nir_src, WarpedVRT(nir_src, **vrt_options) as nir_vrt:
                    nir = nir_vrt.read(1, masked=True).astype("float32") * SR_SCALE + SR_OFFSET
                qa_vrt_options = {**vrt_options, "resampling": Resampling.nearest}
                with rasterio.open(qa_url) as qa_src, WarpedVRT(qa_src, **qa_vrt_options) as qa_vrt:
                    qa = qa_vrt.read(1, masked=True)
                denominator = nir + red
                ndvi = np.full((height, width), np.nan, dtype="float32")
                valid = inside & _clear_pixel_mask(qa) & ~np.ma.getmaskarray(red) & ~np.ma.getmaskarray(nir) & (np.abs(denominator) > 1e-6)
                ndvi[valid] = np.clip((nir[valid] - red[valid]) / denominator[valid], -1, 1)
                scenes.append(ndvi)
                scene_ids.append(item.id)
            except Exception:
                continue
    if not scenes:
        raise LandsatDataError(f"No usable Landsat raster windows were available for {county_name}.")
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="All-NaN slice encountered", category=RuntimeWarning)
        median = np.nanmedian(np.stack(scenes), axis=0).astype("float32")
    nodata = -9999.0
    median[~inside | ~np.isfinite(median)] = nodata
    profile = {"driver": "COG", "height": height, "width": width, "count": 1, "dtype": "float32", "crs": "EPSG:3857", "transform": target_transform, "nodata": nodata, "compress": "DEFLATE", "blocksize": 256, "overview_resampling": "average"}
    temporary = output.with_suffix(".tmp.tif")
    with rasterio.open(temporary, "w", **profile) as destination:
        destination.write(median, 1)
        destination.update_tags(product="median_ndvi", county=county_name, period=f"{month:%Y-%m}", source="Landsat Collection 2 Level-2 via STAC")
    os.replace(temporary, output)
    metadata = {"county": county_name, "period": f"{month:%Y-%m}", "scene_ids": scene_ids, "scene_count": len(scene_ids), "resolution_m": resolution, "qa_filter": ["fill", "dilated_cloud", "cirrus", "cloud", "cloud_shadow", "snow"], "source": "Landsat C2 L2 · STAC remote COGs"}
    metadata_path.write_text(json.dumps(metadata, indent=2))
    return output.resolve(), metadata


@lru_cache(maxsize=128)
def get_landsat_monthly_stats(county_key: str, months_back: int = 12) -> pd.DataFrame:
    """Compute county NDVI from live Landsat STAC assets; cache derived results only."""
    counties = available_counties()
    if county_key not in counties:
        raise LandsatDataError(f"Unknown Twende county: {county_key}")
    county_name = counties[county_key]
    feature = _county_features()[county_name]
    catalog = Client.open(STAC_URL, modifier=sign_inplace)
    current = pd.Timestamp(date.today().replace(day=1))
    rows = []
    for offset in range(months_back, 0, -1):
        month = current - pd.DateOffset(months=offset)
        start, end = _month_bounds(month.year, month.month)
        try:
            search = catalog.search(
                collections=[COLLECTION],
                intersects=feature["geometry"],
                datetime=f"{start}/{end}",
                query={"eo:cloud_cover": {"lt": 45}},
                max_items=8,
            )
            items = sorted(search.items(), key=lambda item: item.properties.get("eo:cloud_cover", 100))[:3]
        except Exception as exc:
            raise LandsatDataError(f"The Landsat STAC search failed for {county_name}: {exc}") from exc
        weighted_sum = 0.0
        pixel_count = 0
        scene_count = 0
        for item in items:
            try:
                result = _scene_ndvi_stats(item, feature["geometry"])
            except Exception:
                continue
            if result:
                mean, count = result
                weighted_sum += mean * count
                pixel_count += count
                scene_count += 1
        ndvi = weighted_sum / pixel_count if pixel_count else np.nan
        drought_index = float(np.clip((0.5 - ndvi) / 0.7, 0, 1)) if np.isfinite(ndvi) else np.nan
        rows.append({
            "month": month.date(),
            "ndvi": round(ndvi, 3) if np.isfinite(ndvi) else np.nan,
            "rain_anomaly": np.nan,
            "drought_index": round(drought_index, 3) if np.isfinite(drought_index) else np.nan,
            "scenes": scene_count,
            "source": "Landsat C2 L2 · STAC",
        })
    frame = pd.DataFrame(rows)
    if frame["ndvi"].notna().sum() == 0:
        raise LandsatDataError(f"No usable Landsat pixels were found for {county_name} in this period.")
    return frame
