# Rangeland Observatory Hub

Rangeland Observatory Hub is a ward-level grassland monitoring and county planning dashboard for Kenya's arid and semi-arid lands (ASALs). It combines vegetation, rainfall, temperature and surface-variability observations with local resource information to support early field verification and grazing decisions.

The dashboard therefore helps users:

- identify wards where grazing condition is poor or deteriorating
- compare current conditions with the usual value for the same month
- distinguish vegetation stress from rainfall and temperature effects;
- find stronger wards within the selected county or directly across its border
- make use of crowd sourcing to record boreholes, animal watering points, nurseries and grass seed banks
- generate a county planning brief for evaluation

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
- **MSDI:** the moving standard deviation of the Landsat 8/9 OLI red band in a 3 × 3-pixel neighbourhood


### Long-term monthly reference

The reference line is fixed by calendar month. For example, the January reference is the mean of all available January county observations across the full archive.
Changing the selected year changes the comparison line but not this long-term monthly reference.

### Next-month trend range

For the next calendar month, the county report fits a linear trend to prior observations of that same month to obtain a probability range. This range represents statistical trend uncertainty; it is not a meteorological forecast.

## Technology stack

- **Application:** Python, Shiny for Python, Uvicorn and Starlette

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


