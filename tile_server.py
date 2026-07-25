"""Local TiTiler service for derived drought-dashboard COG products."""

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
from titiler.core.factory import TilerFactory

app = FastAPI(title="IGAD Drought Tile Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://127.0.0.1:8001", "http://localhost:8000", "http://localhost:8001"],
    allow_methods=["GET"],
    allow_headers=["*"],
)
cog = TilerFactory(router_prefix="/cog")
app.include_router(cog.router, prefix="/cog", tags=["Cloud Optimized GeoTIFF"])
add_exception_handlers(app, DEFAULT_STATUS_CODES)


@app.get("/health")
def health():
    return {"status": "ok"}
