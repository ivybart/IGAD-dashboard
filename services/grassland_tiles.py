"""Serve the local grassland COG to MapLibre as translucent XYZ PNG tiles."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from rio_tiler.io import COGReader
from rio_tiler.models import ImageData
from rio_tiler.utils import render
from starlette.requests import Request
from starlette.responses import Response

ROOT = Path(__file__).parents[1]
COG_PATH = ROOT / "data" / "Raster" / "esa_grassland_samburu_marsabit_isiolo.tif"
TILE_URL = "/grassland_cog_v2/{z}/{x}/{y}.png"
TILE_BOUNDS = (36.186385432544625, -0.08453146823564683, 39.46343958901264, 4.456182798403298)
MIN_ZOOM = 6
MAX_ZOOM = 14
GRASSLAND_COLORMAP = {
    0: (0, 0, 0, 0),
    1: (43, 151, 105, 255),
}


@lru_cache(maxsize=1024)
def _tile_bytes(z: int, x: int, y: int) -> bytes | None:
    """Read one XYZ tile from the COG and display only grassland value 1."""
    if z < MIN_ZOOM or z > MAX_ZOOM or x < 0 or y < 0:
        return None
    try:
        with COGReader(COG_PATH) as cog:
            tile: ImageData = cog.tile(x, y, z, indexes=1)
    except Exception:
        return None
    return render(
        tile.data,
        mask=tile.mask,
        img_format="PNG",
        colormap=GRASSLAND_COLORMAP,
    )


def grassland_tile(request: Request) -> Response:
    z, x, y = (int(request.path_params[key]) for key in ("z", "x", "y"))
    tile = _tile_bytes(z, x, y)
    if tile is None:
        return Response(status_code=404)
    return Response(
        tile,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
