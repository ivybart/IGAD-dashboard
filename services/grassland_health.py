"""Ward grazing-condition analysis from the supplied GCI archive."""

from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
import pandas as pd
from shapely.geometry import shape

from .gee_climate import BOUNDARIES_PATH, WARD_BOUNDARIES_PATH, climate_data

GCI_ORDER = ["Very poor", "Poor", "Moderate", "Good", "Very good"]
STATUS_COLORS = {
    "Very poor": "#991b1b",
    "Poor": "#dc5f45",
    "Moderate": "#e6b94f",
    "Good": "#67a96b",
    "Very good": "#16705c",
}


@lru_cache(maxsize=160)
def _ward_health_for_date(date_key: str) -> pd.DataFrame:
    """Return the supplied GCI observation for every ward in one month."""
    data = climate_data().copy()
    analysis_date = pd.Timestamp(date_key)
    latest_rows = data[data["date"] == analysis_date].copy()
    if latest_rows.empty:
        raise ValueError(f"No GCI records are available for {analysis_date:%B %Y}")

    recent_start = analysis_date - pd.DateOffset(months=2)
    recent = data[data["date"].between(recent_start, analysis_date)]
    earlier = data[data["date"] < recent_start]
    seasonal = earlier[earlier["date"].dt.month.isin(recent["date"].dt.month.unique())]
    keys = ["ADM1_EN", "ADM3_EN"]
    recent_ndvi = recent.groupby(keys)["NDVI"].mean().rename("recent_ndvi")
    baseline_ndvi = seasonal.groupby(keys)["NDVI"].mean().rename("baseline_ndvi")
    rainfall_baseline = seasonal.groupby(keys)["prcp"].mean().rename("rainfall_baseline")

    result = latest_rows.merge(recent_ndvi, on=keys, how="left")
    result = result.merge(baseline_ndvi, on=keys, how="left")
    result = result.merge(rainfall_baseline, on=keys, how="left")
    result["condition"] = result["GCI_class"]
    result["health_score"] = result["GCI"]
    result["ndvi"] = result["NDVI"]
    result["ndvi_change"] = result["recent_ndvi"] - result["baseline_ndvi"]
    result["rainfall"] = result["prcp"]
    result["temperature"] = result["lst"]
    result["rainfall_anomaly_pct"] = np.where(
        result["rainfall_baseline"] > 1,
        100 * (result["rainfall"] - result["rainfall_baseline"]) / result["rainfall_baseline"],
        np.nan,
    )
    return result.sort_values(["health_score", "ADM1_EN", "ADM3_EN"]).reset_index(drop=True)


def ward_health(as_of: pd.Timestamp | str | None = None) -> pd.DataFrame:
    data = climate_data()
    analysis_date = data["date"].max() if as_of is None else pd.Timestamp(as_of)
    return _ward_health_for_date(analysis_date.strftime("%Y-%m-%d")).copy()


def county_health(county_key: str, choices: dict[str, str], as_of: pd.Timestamp | str | None = None) -> pd.DataFrame:
    health = ward_health(as_of)
    return health[health["ADM1_EN"] == choices[county_key]].copy()


def county_signal_series(county_name: str) -> pd.DataFrame:
    subset = climate_data()[climate_data()["ADM1_EN"] == county_name]
    columns = ["NDVI", "GCI", "prcp", "lst"]
    return subset.groupby("date", as_index=False).apply(
        lambda group: pd.Series({
            column: np.average(group.loc[group[column].notna(), column], weights=group.loc[group[column].notna(), "area"])
            if group[column].notna().any() else np.nan
            for column in columns
        }),
        include_groups=False,
    ).reset_index(drop=True)


def county_month_comparison(county_name: str, selected_year: int) -> pd.DataFrame:
    """Compare one year with a fixed monthly climatology using every available year."""
    series = county_signal_series(county_name).copy()
    series["year"] = series["date"].dt.year
    series["month"] = series["date"].dt.month
    signals = ["NDVI", "GCI", "prcp", "lst"]
    baseline = (
        series.groupby("month", as_index=False)[signals]
        .mean()
        .rename(columns={column: f"{column}_average" for column in signals})
    )
    selected = (
        series[series["year"] == selected_year][["month", *signals]]
        .rename(columns={column: f"{column}_selected" for column in signals})
    )
    months = pd.DataFrame({"month": range(1, 13)})
    return months.merge(baseline, on="month", how="left").merge(selected, on="month", how="left")


@lru_cache(maxsize=1)
def _boundary_geometries() -> tuple[dict, dict]:
    counties = {
        feature["properties"]["ADM1_EN"].strip(): shape(feature["geometry"])
        for feature in json.loads(BOUNDARIES_PATH.read_text())["features"]
    }
    wards = {
        (feature["properties"]["ADM1_EN"].strip(), feature["properties"]["ADM3_EN"].strip()): shape(feature["geometry"])
        for feature in json.loads(WARD_BOUNDARIES_PATH.read_text())["features"]
    }
    return counties, wards


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    lat1r, lat2r = np.radians([lat1, lat2])
    delta_lat = lat2r - lat1r
    delta_lon = np.radians(lon2 - lon1)
    value = np.sin(delta_lat / 2) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(delta_lon / 2) ** 2
    return float(2 * radius * np.arcsin(np.sqrt(value)))


def movement_recommendations(county_name: str, as_of: pd.Timestamp | str | None = None, limit: int = 3) -> list[dict]:
    health = ward_health(as_of)
    origin = health[(health["ADM1_EN"] == county_name) & health["condition"].isin(["Very poor", "Poor"])]
    if origin.empty:
        return []
    counties, ward_geometries = _boundary_geometries()
    county_geometry = counties[county_name]
    candidates = health[health["condition"].isin(["Good", "Very good"])].copy()
    if candidates.empty:
        return []
    candidates["relation"] = candidates.apply(
        lambda row: "Within selected county" if row["ADM1_EN"] == county_name else (
            "Border ward" if ward_geometries[(row["ADM1_EN"], row["ADM3_EN"])].distance(county_geometry) < 1e-6 else ""
        ), axis=1,
    )
    candidates = candidates[candidates["relation"] != ""]
    if candidates.empty:
        return []
    candidates["distance_km"] = candidates.apply(
        lambda destination: min(
            _distance_km(destination["latitude"], destination["longitude"], source["latitude"], source["longitude"])
            for _, source in origin.iterrows()
        ), axis=1,
    )
    candidates = candidates[candidates["distance_km"] <= 150].sort_values(
        ["distance_km", "health_score"], ascending=[True, False]
    ).head(limit)
    origins = ", ".join(origin.sort_values("health_score")["ADM3_EN"].head(4))
    return [{
        "origin_wards": origins,
        "ADM1_EN": row.ADM1_EN,
        "ADM3_EN": row.ADM3_EN,
        "score": row.health_score,
        "distance_km": row.distance_km,
        "relation": row.relation,
    } for row in candidates.itertuples()]


def ward_health_geojson(focus_county: str | None = None, as_of: pd.Timestamp | str | None = None) -> dict:
    """Join a selected month's GCI class to every supplied ward polygon."""
    health = ward_health(as_of).set_index(["ADM1_EN", "ADM3_EN"])
    geojson = json.loads(WARD_BOUNDARIES_PATH.read_text())
    matched = 0
    for feature in geojson["features"]:
        properties = feature["properties"]
        key = (properties["ADM1_EN"].strip(), properties["ADM3_EN"].strip())
        if key not in health.index:
            properties.update({
                "fill_color": "#7f8c87", "indicator": "GCI", "display_value": "No data",
                "in_focus": focus_county is None,
            })
            continue
        row = health.loc[key]
        matched += 1
        temperature_detail = (
            f"Land temperature {row['lst']:.1f} °C"
            if pd.notna(row["lst"])
            else "Land temperature unavailable"
        )
        properties.update({
            "fill_color": STATUS_COLORS.get(row["condition"], "#7f8c87"),
            "indicator": f"Grazing condition · {row['condition']}",
            "display_value": f"GCI {row['health_score']:.1f}",
            "detail_1": f"NDVI {row['NDVI']:.3f}",
            "detail_2": f"Rainfall {row['prcp']:.1f} mm",
            "detail_3": temperature_detail,
            "in_focus": focus_county is None or key[0] == focus_county,
        })
    if matched != len(health):
        raise ValueError(f"Ward boundary join matched {matched} of {len(health)} latest GCI records")
    return geojson


def county_health_geojson() -> dict:
    health = ward_health()
    summary = health.groupby("ADM1_EN").agg(
        score=("health_score", "mean"),
        priority=("condition", lambda values: int(values.isin(["Very poor", "Poor"]).sum())),
    )
    geojson = json.loads(BOUNDARIES_PATH.read_text())
    for feature in geojson["features"]:
        name = feature["properties"]["ADM1_EN"].strip()
        row = summary.loc[name]
        index = min(4, max(0, int(row["score"] // 20)))
        condition = GCI_ORDER[index]
        feature["properties"].update({
            "fill_color": STATUS_COLORS[condition],
            "indicator": "Mean grazing condition",
            "display_value": f"GCI {row['score']:.1f} · {int(row['priority'])} poor/very poor wards",
        })
    return geojson
