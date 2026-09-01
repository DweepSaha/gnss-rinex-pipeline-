"""
FastAPI backend for GNSS Positioning Quality Analyzer.
Exposes the existing SPP pipeline as a REST API.
Run with: uvicorn api:app --reload --port 8000
"""

from __future__ import annotations

import datetime
import io
import math
import tempfile
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from gnss_processor import (
    compute_summary,
    make_error_timeseries,
    make_scatter_plot,
    make_sky_plot,
    make_snr_heatmap,
    process_session,
)
from src.gnss_pipeline.pdf_report import build_pdf_report

app = FastAPI(title="GNSS Quality Analyzer API")

# Allow the browser to call this API from a file:// origin (frontend/index.html
# opened directly) as well as from a local HTTP server on any port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok", "service": "GNSS Quality Analyzer API"}

def _save_upload(upload: UploadFile) -> str:
    """Save a FastAPI UploadFile to a temp path and return that path."""
    suffix = Path(upload.filename or "upload").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(upload.file.read())
        return f.name


def _clean_for_json(value):
    """Recursively convert numpy / datetime types and NaN / Inf into
    JSON-safe values. snr_results / cmc_results carry numpy datetime64
    "epochs" arrays and numpy float/bool arrays that the default JSON
    encoder cannot handle."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _clean_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean_for_json(v) for v in value]
    if isinstance(value, np.ndarray):
        return _clean_for_json(value.tolist())
    if isinstance(value, np.floating):
        return _clean_for_json(float(value))
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (np.datetime64, datetime.datetime, datetime.date)):
        return str(value)
    return value


def _strip_epochs(sat_results: dict) -> dict:
    """Drop the raw datetime "epochs" array from each satellite's SNR/CMC
    result dict - it is not part of the documented response shape and the
    frontend has no use for it (it already has errors_h/errors_v timelines)."""
    cleaned = {}
    for sat, entry in (sat_results or {}).items():
        cleaned[sat] = {k: v for k, v in entry.items() if k != "epochs"}
    return cleaned


@app.post("/analyze")
async def analyze(
    obs_file: UploadFile = File(...),
    nav_file: UploadFile = File(...),
    ref_lat: float = Form(...),
    ref_lon: float = Form(...),
    ref_h: float = Form(...),
    max_epochs: int = Form(120),
):
    obs_path = None
    nav_path = None
    try:
        try:
            obs_path = _save_upload(obs_file)
            nav_path = _save_upload(nav_file)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not save uploaded files: {e}")

        try:
            results = process_session(
                obs_path, nav_path, ref_lat, ref_lon, ref_h, max_epochs,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Processing failed: {e}")

        if results["n_processed"] < 4:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Not enough observations processed. Check that your reference "
                    "coordinates are correct, both files cover the same date, and "
                    "the observation file contains GPS data."
                ),
            )

        try:
            stats, mean_hdop, mean_pdop = compute_summary(results)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Statistics computation failed: {e}")

        results.pop("actual_obs_path", None)
        results["snr_results"] = _strip_epochs(results.get("snr_results", {}))
        results["cmc_results"] = _strip_epochs(results.get("cmc_results", {}))

        response = {
            "results": results,
            "stats": stats,
            "mean_hdop": mean_hdop,
            "mean_pdop": mean_pdop,
            "ref_lat": ref_lat,
            "ref_lon": ref_lon,
            "ref_h": ref_h,
            "obs_filename": obs_file.filename or "",
            "nav_filename": nav_file.filename or "",
        }
        return JSONResponse(content=_clean_for_json(response))

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected server error: {e}")
    finally:
        for p in (obs_path, nav_path):
            if p:
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass


class ReportRequest(BaseModel):
    results:      dict
    stats:        dict
    mean_hdop:    float
    mean_pdop:    float
    ref_lat:      float
    ref_lon:      float
    ref_h:        float
    obs_filename: str = ""
    nav_filename: str = ""


@app.post("/report")
def report(payload: ReportRequest):
    """Rebuild the Plotly figures from the raw result arrays and hand them,
    together with the stats already computed by /analyze, to the existing
    build_pdf_report() to produce the downloadable PDF."""
    try:
        results = payload.results
        flags          = results.get("combined_flags", {}) or {}
        errors_h       = results.get("errors_h", []) or []
        errors_v       = results.get("errors_v", []) or []
        north_errors   = results.get("north_errors", []) or []
        east_errors    = results.get("east_errors", []) or []
        dop_list       = results.get("dop_list", []) or []
        snr_results    = results.get("snr_results", {}) or {}
        sat_sky_track  = results.get("sat_sky_track", {}) or {}
        epoch_interval = results.get("epoch_interval_seconds", 30.0)

        fig_scatter = (
            make_scatter_plot(north_errors, east_errors, errors_h)
            if errors_h else None
        )
        fig_ts = (
            make_error_timeseries(errors_h, errors_v, dop_list, epoch_interval)
            if errors_h else None
        )
        fig_snr = make_snr_heatmap(snr_results) if snr_results else None
        fig_sky = (
            make_sky_plot(sat_sky_track, flags, snr_results)
            if sat_sky_track else None
        )

        pdf_bytes = build_pdf_report(
            results=results,
            stats=payload.stats,
            flags=flags,
            mean_hdop=payload.mean_hdop,
            mean_pdop=payload.mean_pdop,
            ref_lat=payload.ref_lat,
            ref_lon=payload.ref_lon,
            ref_h=payload.ref_h,
            obs_filename=payload.obs_filename,
            nav_filename=payload.nav_filename,
            fig_scatter=fig_scatter,
            fig_sky=fig_sky,
            fig_snr=fig_snr,
            fig_timeseries=fig_ts,
        )
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=GNSS_Quality_Report.pdf",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")
