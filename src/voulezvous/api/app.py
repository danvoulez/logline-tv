from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from voulezvous.api.routers import assets, health, plans, prep, reports, stream
from voulezvous.config import settings
from voulezvous.logging_config import setup_logging

setup_logging()

app = FastAPI(title="Voulezvous Streaming Engine", version="0.1.0")

# Static files and templates
_pkg_dir = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=str(_pkg_dir / "static")), name="static")
templates = Jinja2Templates(directory=str(_pkg_dir / "templates"))

# Mount HLS spool dir for live segment serving
settings.ensure_spool_dirs()
app.mount("/hls", StaticFiles(directory=str(settings.spool_hls)), name="hls")

# API routers
app.include_router(health.router)
app.include_router(assets.router)
app.include_router(plans.router)
app.include_router(prep.router)
app.include_router(stream.router)
app.include_router(reports.router)


@app.get("/", response_class=HTMLResponse)
async def client_page(request: Request):
    return templates.TemplateResponse("client.html", {"request": request})


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})
