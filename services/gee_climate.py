"""Read and aggregate the supplied Google Earth Engine climate export."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1]
CSV_PATH = ROOT / "data" / "gee_climate_202604.csv"
BOUNDARIES_PATH = ROOT / "data" / "Kenya_adm1_twende.geojson"

INDICATORS = {
    "NDVI": {"label": "Vegetation greenness", "short": "NDVI", "unit": "", "palette": ["#7f1d1d", "#dc6b42", "#f1c453", "#88b35b", "#19705d"]},
    "prcp": {"label": "Monthly precipitation", "short": "Rainfall", "unit": "mm", "palette": ["#8b4513", "#d79a4b", "#efe0a3", "#76b5c5", "#155e75"]},
    "lst": {"label": "Land surface temperature", "short": "LST", "unit": "°C", "palette": ["#1d4e89", "#75aadb", "#f2d479", "#e88945", "#a82323"]},
    "sm": {"label": "Soil moisture", "short": "Soil moisture", "unit": "m³/m³", "palette": ["#8c4f2b", "#d29b63", "#e8ddaa", "#6ab0a8", "#16635d"]},
    "vci": {"label": "Vegetation Condition Index", "short": "VCI", "unit": "", "palette": ["#b42318", "#e36f38", "#f1c453", "#88b35b", "#19705d"]},
    "tci": {"label": "Temperature Condition Index", "short": "TCI", "unit": "", "palette": ["#b42318", "#e36f38", "#f1c453", "#88b35b", "#19705d"]},
    "pci": {"label": "Precipitation Condition Index", "short": "PCI", "unit": "", "palette": ["#b42318", "#e36f38", "#f1c453", "#88b35b", "#19705d"]},
    "spi": {"label": "Standardized Precipitation Index", "short": "SPI", "unit": "", "palette": ["#a82323", "#e88945", "#f2d479", "#75aadb", "#1d4e89"]},
    "smdi": {"label": "Soil Moisture Deficit Index", "short": "SMDI", "unit": "", "palette": ["#a82323", "#e88945", "#f2d479", "#75aadb", "#1d4e89"]},
    "cdi": {"label": "Combined Drought Index", "short": "CDI", "unit": "", "palette": ["#b42318", "#e36f38", "#f1c453", "#88b35b", "#19705d"]},
    "cdi3": {"label": "Three-month Combined Drought Index", "short": "CDI-3", "unit": "", "palette": ["#b42318", "#e36f38", "#f1c453", "#88b35b", "#19705d"]},
}


@lru_cache(maxsize=1)
def climate_data() -> pd.DataFrame:
    frame = pd.read_csv(CSV_PATH, parse_dates=["date"])
    return frame.sort_values(["ADM1_EN", "date"])


def county_choices() -> dict[str, str]:
    names = sorted(climate_data()["ADM1_EN"].unique())
    return {name.lower().replace(" ", "_"): name for name in names}


def county_name(key: str) -> str:
    return county_choices()[key]


def _weighted(group: pd.DataFrame, indicator: str) -> float:
    valid = group[[indicator, "area"]].dropna()
    if valid.empty:
        return np.nan
    return float(np.average(valid[indicator], weights=valid["area"]))


def county_series(county_key: str, indicator: str, months: int = 36) -> pd.DataFrame:
    data = climate_data()
    subset = data[data["ADM1_EN"] == county_name(county_key)]
    series = subset.groupby("date", as_index=False).apply(
        lambda group: pd.Series({"value": _weighted(group, indicator), "wards": group["ADM3_EN"].nunique()}),
        include_groups=False,
    )
    return series.tail(months).reset_index(drop=True)


def latest_snapshot(indicator: str) -> pd.DataFrame:
    data = climate_data()
    latest = data["date"].max()
    subset = data[data["date"] == latest]
    rows = [
        {"ADM1_EN": name, "value": _weighted(group, indicator), "wards": group["ADM3_EN"].nunique()}
        for name, group in subset.groupby("ADM1_EN")
    ]
    return pd.DataFrame(rows), latest


def latest_county_metrics(county_key: str) -> dict:
    data = climate_data()
    latest = data["date"].max()
    group = data[(data["ADM1_EN"] == county_name(county_key)) & (data["date"] == latest)]
    values = {indicator: _weighted(group, indicator) for indicator in INDICATORS}
    return {**values, "date": latest, "wards": int(group["ADM3_EN"].nunique()), "landscape": group["landscape"].iloc[0]}


def drought_phase(cdi3: float) -> str:
    if not np.isfinite(cdi3):
        return "No data"
    if cdi3 < 30:
        return "Warning"
    if cdi3 < 40:
        return "Alert"
    if cdi3 < 50:
        return "Watch"
    return "Normal"


def _color(value: float, low: float, high: float, palette: list[str]) -> str:
    if not np.isfinite(value):
        return "#9ca8a3"
    position = 0.5 if high == low else (value - low) / (high - low)
    return palette[min(4, max(0, int(position * 4.999)))]


def indicator_geojson(indicator: str) -> tuple[dict, dict]:
    snapshot, latest = latest_snapshot(indicator)
    values = snapshot.set_index("ADM1_EN")["value"].to_dict()
    finite = snapshot["value"].dropna()
    low, high = float(finite.min()), float(finite.max())
    definition = INDICATORS[indicator]
    geojson = json.loads(BOUNDARIES_PATH.read_text())
    for feature in geojson["features"]:
        name = feature["properties"]["ADM1_EN"]
        value = values.get(name, np.nan)
        formatted = format_value(indicator, value)
        feature["properties"].update({
            "fill_color": _color(value, low, high, definition["palette"]),
            "indicator": definition["short"],
            "display_value": formatted,
            "raw_value": None if not np.isfinite(value) else float(value),
        })
    return geojson, {"date": latest, "min": low, "max": high, "palette": definition["palette"], "label": definition["label"], "unit": definition["unit"]}


def format_value(indicator: str, value: float) -> str:
    if not np.isfinite(value):
        return "No data"
    unit = INDICATORS[indicator]["unit"]
    decimals = 3 if indicator in ("NDVI", "sm") else 1
    return f"{value:.{decimals}f}{' ' + unit if unit else ''}"
