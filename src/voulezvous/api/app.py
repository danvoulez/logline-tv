from fastapi import FastAPI

from voulezvous.api.routers import assets, health, plans, prep, reports, stream
from voulezvous.logging_config import setup_logging

setup_logging()

app = FastAPI(title="Voulezvous Streaming Engine", version="0.1.0")

app.include_router(health.router)
app.include_router(assets.router)
app.include_router(plans.router)
app.include_router(prep.router)
app.include_router(stream.router)
app.include_router(reports.router)
