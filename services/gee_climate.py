"""Read and aggregate the supplied Google Earth Engine climate export."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1]
CSV_PATH = ROOT / "data" / "merged_ward_indicators_with_gci.csv"
BOUNDARIES_PATH = ROOT / "data" / "ASAL_Counties.geojson"
WARD_BOUNDARIES_PATH = ROOT / "data" / "ASAL_wards.geojson"

@lru_cache(maxsize=1)
def climate_data() -> pd.DataFrame:
    frame = pd.read_csv(CSV_PATH, parse_dates=["date"])
    frame.loc[frame["lst"] < 0, "lst"] = np.nan
    boundaries = json.loads(WARD_BOUNDARIES_PATH.read_text())
    attributes = pd.DataFrame([
        {
            "ward_name": feature["properties"]["ADM3_EN"].strip(),
            "ADM3_EN": feature["properties"]["ADM3_EN"].strip(),
            "ADM1_EN": feature["properties"]["ADM1_EN"].strip(),
            "ADM2_EN": feature["properties"].get("ADM2_EN", "").strip(),
            "landscape": feature["properties"].get("landscape", ""),
            "area": feature["properties"].get("area", 1.0),
            "longitude": feature["properties"].get("longitude"),
            "latitude": feature["properties"].get("latitude"),
        }
        for feature in boundaries["features"]
    ]).drop_duplicates("ward_name")
    frame["ward_name"] = frame["ward_name"].str.strip()
    frame["GCI_class"] = frame["GCI_class"].fillna("No data").str.strip().str.capitalize()
    frame = frame.merge(attributes, on="ward_name", how="left", validate="many_to_one")
    if frame["ADM3_EN"].isna().any():
        missing = sorted(frame.loc[frame["ADM3_EN"].isna(), "ward_name"].unique())
        raise ValueError(f"CSV wards missing from ASAL_wards.geojson: {missing}")
    return frame.sort_values(["ADM1_EN", "ADM3_EN", "date"]).reset_index(drop=True)


def county_choices() -> dict[str, str]:
    names = sorted(climate_data()["ADM1_EN"].unique())
    return {name.lower().replace(" ", "_"): name for name in names}
