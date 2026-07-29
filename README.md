# Rangeland Observatory Hub

Rangeland Observatory Hub is a ward-level grassland monitoring and county planning dashboard for Kenya's arid and semi-arid lands (ASALs). It combines vegetation, rainfall, temperature and surface-variability observations with local resource information to support early field verification and grazing decisions.

## Why monitor grasslands?

Pastoral livelihoods depend on grass condition, water access and the ability to respond before local degradation becomes severe. Rainfall alone does not describe usable forage: vegetation may respond slowly, heat can increase water stress, and apparently green areas may still be fragmented or inaccessible.

The dashboard therefore helps users:

- identify wards where grazing condition is poor or deteriorating;
- compare current conditions with the usual value for the same month;
- distinguish vegetation stress from rainfall and temperature effects;
- find stronger wards within the selected county or directly across its border;
- review boreholes, animal watering points, nurseries and grass seed banks; and
- generate a county planning brief for field discussion.

This is a screening tool, not a movement instruction or weather forecast. Recommendations must be checked against water availability, land tenure, conflict risk, resource ownership and local authority guidance.

## Indicators and formulas

### Grazing Condition Index

The input archive supplies a monthly Grazing Condition Index (GCI) for each ward. Its conceptual weighting is:

```text
GCI = 0.35 × NDVI_score
    + 0.25 × rainfall_score
    + 0.20 × (100 - temperature_score)
    + 0.20 × (100 - MSDI_score)
```

Each component is normalized to a common 0–100 scale before weighting. Temperature and MSDI are reverse-scored because excess heat and high local red-band variability reduce the grazing-condition score.

| GCI | Classification |
| ---: | --- |
| 0–19.9 | Very poor |
| 20–39.9 | Poor |
| 40–59.9 | Moderate |
| 60–79.9 | Good |
| 80–100 | Very good |

### Supporting indicators

- **NDVI:** `(NIR - Red) / (NIR + Red)`. Higher values generally indicate greener, more photosynthetically active vegetation.
- **Rainfall:** monthly precipitation total in millimetres.
- **Temperature:** monthly land-surface temperature in degrees Celsius. Negative source values are treated as missing data.
- **MSDI:** the moving standard deviation of the Landsat red band in a 3 × 3-pixel neighbourhood:

```text
MSDI(i, j) = standard_deviation(Red values in the 3 × 3 window around pixel i, j)
```

### County aggregation

Ward observations are aggregated using ward area as the weight:

```text
county_value = Σ(ward_value × ward_area) / Σ(ward_area)
```

Only wards with a valid value for the selected indicator participate in that indicator's calculation.

### Long-term monthly reference

The reference line is fixed by calendar month. For example, the January reference is the mean of all available January county observations across the full archive:

```text
LTA(month m) = mean(county observations where calendar_month = m)
```

Changing the selected year changes the comparison line but not this long-term monthly reference.

### Rainfall anomaly

```text
rainfall_anomaly_percent = 100 × (current_rainfall - baseline_rainfall) / baseline_rainfall
```

The calculation is omitted when the baseline is missing or too close to zero.

### Next-month trend range

For the next calendar month, the county report fits a linear trend to prior observations of that same month:

```text
y = intercept + slope × year
forecast = intercept + slope × target_year
95% range = forecast ± 1.96 × prediction_error
```

At least three prior observations are required. Physical bounds are applied where appropriate, such as GCI `0–100`, NDVI `-1–1`, and non-negative rainfall. This range represents statistical trend uncertainty; it is not a meteorological forecast.

## Technology stack

- **Application:** Python, Shiny for Python, Uvicorn and Starlette
- **Analysis:** pandas and NumPy
- **Vector geospatial processing:** GeoPandas and Shapely
- **Resource storage:** GeoPackage through Pyogrio
- **Maps:** MapLibre GL JS with OpenFreeMap basemaps
- **Raster tiles:** Rio-tiler serving the local cloud-optimized GeoTIFF on demand
- **Charts:** Plotly
- **Reports:** ReportLab PDF generation
- **Place search:** packaged GeoNames Kenya gazetteer
- **Interface:** HTML, CSS, Bootstrap icons and small JavaScript helpers loaded by Shiny

## Project layout

```text
app.py                  Shiny application and ASGI entry point
modules/                Overview, grassland health and county planning UI/server modules
services/               Climate, spatial, raster, resource and PDF services
www/                    Styles and browser-side map/location helpers
requirements.txt        Python runtime dependencies
```

## Install and launch

Run these commands from the project directory using Bash:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in a browser.

To stop the server, press `Ctrl+C`. To leave the virtual environment:

```bash
deactivate
```

For access from another machine on the same trusted network, bind to all interfaces:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```


