"""Shared demo data and domain constants."""

import random

import pandas as pd

from services.gee_climate import INDICATORS as GEE_INDICATORS, county_choices

INDICATORS = {key: value["label"] for key, value in GEE_INDICATORS.items()}
AOIS = county_choices()

STATUS_COLORS = {
    "Normal": "#27866f",
    "Watch": "#e2a93b",
    "Alert": "#dc7b31",
    "Warning": "#c94b4b",
}

AREA_POINTS = pd.DataFrame(
    [
        {"key": "makueni", "name": "Makueni County", "country": "Kenya", "lat": -2.25, "lon": 37.89, "phase": "Watch", "people": 184000, "water": 42},
        {"key": "taita_taveta", "name": "Taita Taveta County", "country": "Kenya", "lat": -3.32, "lon": 38.48, "phase": "Alert", "people": 127000, "water": 36},
        {"key": "brcis_somalia", "name": "BRCiS Somalia", "country": "Somalia", "lat": 2.05, "lon": 45.32, "phase": "Warning", "people": 316000, "water": 28},
        {"key": "mandera", "name": "Mandera Triangle", "country": "Kenya / Ethiopia / Somalia", "lat": 3.94, "lon": 41.86, "phase": "Alert", "people": 209000, "water": 33},
        {"key": "karamoja", "name": "Karamoja Cluster", "country": "Uganda / Kenya", "lat": 2.65, "lon": 34.55, "phase": "Watch", "people": 143000, "water": 51},
    ]
)

FACILITY_POINTS = pd.DataFrame(
    [
        {"name": "Kathonzweni borehole", "type": "Water", "lat": -2.17, "lon": 37.73, "status": "Operational", "capacity": 72},
        {"name": "Voi distribution hub", "type": "Relief", "lat": -3.40, "lon": 38.56, "status": "Low stock", "capacity": 38},
        {"name": "Dadaab clinic", "type": "Health", "lat": 0.06, "lon": 40.31, "status": "Operational", "capacity": 64},
        {"name": "Taveta feed bank", "type": "Livestock", "lat": -3.40, "lon": 37.68, "status": "Needs attention", "capacity": 31},
        {"name": "Mandera water depot", "type": "Water", "lat": 3.94, "lon": 41.86, "status": "Low stock", "capacity": 35},
    ]
)

REPORT_POINTS = pd.DataFrame(
    [
        {"name": "Dry community water point", "type": "Water shortage", "lat": -2.21, "lon": 37.81, "status": "New"},
        {"name": "Livestock movement", "type": "Livestock health", "lat": 1.72, "lon": 44.76, "status": "Verified"},
        {"name": "Crop wilting observed", "type": "Crop stress", "lat": -3.18, "lon": 38.33, "status": "Priority"},
    ]
)


def east_africa_map_layout(height: int = 390) -> dict:
    """Shared geographic styling for all Plotly maps."""
    return {
        "height": height,
        "margin": {"l": 0, "r": 0, "t": 0, "b": 0},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": "DM Sans", "color": "#52635f"},
        "geo": {
            "projection_type": "equirectangular",
            "showframe": False,
            "showcoastlines": True,
            "coastlinecolor": "#a8b8b0",
            "showland": True,
            "landcolor": "#e8eee8",
            "showocean": True,
            "oceancolor": "#dcebed",
            "showlakes": True,
            "lakecolor": "#dcebed",
            "showcountries": True,
            "countrycolor": "#bcc9c3",
            "lataxis_range": [-6, 8],
            "lonaxis_range": [31, 49],
            "bgcolor": "rgba(0,0,0,0)",
        },
        "showlegend": False,
    }


def classify_status(df: pd.DataFrame) -> str:
    last3 = df["drought_index"].dropna().tail(3).tolist()
    if not last3:
        return "Normal"
    if len(last3) >= 3 and all(value >= 0.75 for value in last3):
        return "Warning"
    if len(last3) >= 2 and all(value >= 0.55 for value in last3[-2:]):
        return "Alert"
    if last3[-1] >= 0.35:
        return "Watch"
    return "Normal"


def get_resources(aoi_key: str) -> pd.DataFrame:
    seed = sum(ord(char) for char in aoi_key) + 99
    random.seed(seed)
    resources = [
        ("Water points", 42),
        ("Relief stock", 68),
        ("Mobile clinics", 55),
        ("Feed reserves", 31),
    ]
    return pd.DataFrame(
        [
            {
                "resource": name,
                "availability": max(12, min(94, base + random.randint(-9, 9))),
                "operational": random.randint(6, 18),
            }
            for name, base in resources
        ]
    )


def get_facilities(aoi_key: str) -> pd.DataFrame:
    random.seed(sum(ord(char) for char in aoi_key) + 211)
    names = ["Kathonzweni borehole", "Voi distribution hub", "Dadaab clinic", "Taveta feed bank"]
    return pd.DataFrame(
        {
            "Facility": names,
            "Type": ["Water", "Relief", "Health", "Livestock"],
            "Status": ["Operational", "Low stock", "Operational", "Needs attention"],
            "Capacity": [f"{random.randint(35, 91)}%" for _ in names],
            "Last check": ["Today", "Yesterday", "2 days ago", "3 days ago"],
        }
    )
