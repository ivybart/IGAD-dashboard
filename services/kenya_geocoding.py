"""Offline Kenya place autocomplete backed by the GeoNames country extract."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from zipfile import ZipFile


GAZETTEER_PATH = Path(__file__).resolve().parents[1] / "data" / "gazetteer" / "KE.zip"
GEONAMES_COLUMNS = (
    "geoname_id", "name", "ascii_name", "alternate_names", "latitude", "longitude",
    "feature_class", "feature_code", "country_code", "alternate_country_codes",
    "admin1", "admin2", "admin3", "admin4", "population", "elevation", "dem",
    "timezone", "modified",
)
PLACE_TYPES = {
    "PPLC": "capital",
    "PPLA": "county seat",
    "PPLA2": "administrative centre",
    "PPLA3": "administrative centre",
    "PPLA4": "administrative centre",
    "PPL": "town / settlement",
    "PPLG": "government seat",
    "PPLL": "populated locality",
    "PPLQ": "former settlement",
    "PPLR": "religious settlement",
    "PPLS": "settlements",
}


@lru_cache(maxsize=1)
def kenya_places() -> tuple[dict, ...]:
    """Load populated places from the packaged GeoNames Kenya extract."""
    if not GAZETTEER_PATH.exists():
        raise FileNotFoundError(f"Kenya gazetteer not found at {GAZETTEER_PATH}")

    places: list[dict] = []
    with ZipFile(GAZETTEER_PATH) as archive:
        with archive.open("KE.txt") as source:
            for raw_line in source:
                values = raw_line.decode("utf-8").rstrip("\n").split("\t")
                if len(values) != len(GEONAMES_COLUMNS):
                    continue
                row = dict(zip(GEONAMES_COLUMNS, values))
                if row["feature_class"] != "P":
                    continue
                population = int(row["population"] or 0)
                place_type = PLACE_TYPES.get(row["feature_code"], "settlement")
                places.append(
                    {
                        "id": row["geoname_id"],
                        "name": row["name"],
                        "ascii_name": row["ascii_name"],
                        "latitude": float(row["latitude"]),
                        "longitude": float(row["longitude"]),
                        "population": population,
                        "place_type": place_type,
                    }
                )
    places.sort(key=lambda item: (-item["population"], item["name"].casefold()))
    return tuple(places)


@lru_cache(maxsize=1)
def kenya_place_index() -> dict[str, dict]:
    return {place["id"]: place for place in kenya_places()}


@lru_cache(maxsize=1)
def kenya_place_choices() -> dict[str, str]:
    """Return Selectize choices ordered by population then name."""
    return {
        place["id"]: (
            f"{place['name']} - {place['place_type']} "
            f"({place['latitude']:.4f}, {place['longitude']:.4f})"
        )
        for place in kenya_places()
    }


def get_kenya_place(geoname_id: str) -> dict | None:
    place = kenya_place_index().get(str(geoname_id))
    return dict(place) if place else None
