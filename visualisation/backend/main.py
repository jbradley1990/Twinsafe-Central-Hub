from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pathlib import Path

from .config import FRONTEND_DIR, PDF_DIR
from .pages import rig_overview, pdf_generation, historical_trend

app = FastAPI(title="Twinsafe Central Hub")

WEBVISU_URL = "http://10.1.6.7:9000"  # ← adjust to your HMI

@app.middleware("http")
async def bounce_portal_host(request: Request, call_next):
    host = request.url.hostname or ""
    if host.lower() == "rnd-portal.valves.co.uk":
        return RedirectResponse(url=WEBVISU_URL)
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Page-specific routers
app.include_router(rig_overview.router)
app.include_router(pdf_generation.router)
app.include_router(historical_trend.router)

# Health check
@app.get("/api/ping")
async def ping():
    return {"ok": True}

# Root redirect to Rig Overview
@app.get("/")
async def root():
    return RedirectResponse(url="/pages/rig-overview.html")

@app.get("/rig-overview")
async def rig_overview_legacy():
    return RedirectResponse(url="/pages/rig-overview.html")

@app.get("/getting-started")
async def getting_started_legacy():
    return RedirectResponse(url="/pages/getting-started.html")

@app.get("/pdf-chart-generation")
async def pdf_chart_generation_legacy():
    return RedirectResponse(url="/pages/pdf-chart-generation.html")

@app.get("/historical-trend")
async def historical_trend_legacy():
    return RedirectResponse(url="/pages/historical-trend.html")

# Serve Frontend static files
# We mount the subdirectories at the root paths to support relative links from /pages/*.html
app.mount("/pages", StaticFiles(directory=str(FRONTEND_DIR / "pages")), name="pages")
app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")
app.mount("/styles", StaticFiles(directory=str(FRONTEND_DIR / "styles")), name="styles")

# Support guide assets used in Getting Started page
import os
if os.path.exists("guide"):
    app.mount("/guide", StaticFiles(directory="guide"), name="guide")
elif os.path.exists("Getting-Started/guide"):
    app.mount("/guide", StaticFiles(directory="Getting-Started/guide"), name="guide")

# Mount any other top-level frontend assets if they exist (e.g. favicon)
if FRONTEND_DIR.exists():
    # Only mount if directory isn't already covered
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
