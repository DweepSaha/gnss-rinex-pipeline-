"""
PDF Report Generator for GNSS Positioning Quality Analyzer.

Generates a downloadable professional PDF report from a completed
analysis session. Called after process_session() completes in app.py.

Dependencies: fpdf2, matplotlib, numpy
"""
from __future__ import annotations

import io
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
from fpdf import FPDF, XPos, YPos


# Colour palette (RGB tuples)
C_DARK       = (18,  18,  30)
C_GREEN      = (29, 158, 117)
C_AMBER      = (186, 117,  23)
C_RED        = (216,  90,  48)
C_WHITE      = (255, 255, 255)
C_LIGHT_GREY = (240, 240, 245)
C_MID_GREY   = (180, 180, 190)
C_TEXT       = ( 30,  30,  45)


def _fig_to_png_bytes(fig) -> bytes:
    """Convert matplotlib or Plotly figure to PNG bytes."""
    import io
    # Check if it is a Plotly figure
    if hasattr(fig, "to_image"):
        return fig.to_image(format="png", width=1000, height=500, scale=2)
    # Fallback for matplotlib
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    return buf.read()


def _cep50_colour(cep50: float) -> tuple:
    if cep50 < 50:  return C_GREEN
    if cep50 < 150: return C_AMBER
    return C_RED


def _hdop_colour(hdop: float) -> tuple:
    if hdop < 1.5:  return C_GREEN
    if hdop < 2.0:  return C_AMBER
    return C_RED


def _flag_colour(flag: str) -> tuple:
    return {
        "clean":     C_GREEN,
        "suspect":   C_AMBER,
        "multipath": C_RED,
    }.get(flag, C_MID_GREY)


class GNSSReport(FPDF):
    """Custom FPDF subclass with branded header and footer."""

    def __init__(self, obs_filename: str = "", nav_filename: str = ""):
        super().__init__()
        self.obs_filename = obs_filename
        self.nav_filename = nav_filename
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(left=15, top=15, right=15)

    def header(self):
        self.set_fill_color(*C_DARK)
        self.rect(0, 0, 210, 14, style="F")
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*C_WHITE)
        self.set_y(3)
        self.cell(0, 8,
                  "GNSS Positioning Quality Analyzer  |  "
                  "Geodesy & Geomatics Engineering  |  "
                  "University of New Brunswick",
                  align="C")
        self.set_text_color(*C_TEXT)
        self.ln(10)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*C_MID_GREY)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        self.cell(0, 5,
                  f"Generated {ts}  |  Page {self.page_no()}  |  "
                  "Educational / research use only",
                  align="C")
        self.set_text_color(*C_TEXT)

    def section_title(self, title: str):
        self.ln(4)
        self.set_fill_color(*C_DARK)
        self.set_text_color(*C_WHITE)
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 7, f"  {title}", new_x=XPos.LMARGIN,
                  new_y=YPos.NEXT, fill=True)
        self.set_text_color(*C_TEXT)
        self.ln(2)

    def kv_row(self, key: str, value: str,
               fill: bool = False,
               value_colour: Optional[tuple] = None):
        self.set_font("Helvetica", "", 9)
        self.set_fill_color(*C_LIGHT_GREY)
        self.set_text_color(*C_TEXT)
        self.cell(70, 6, key, fill=fill,
                  new_x=XPos.RIGHT, new_y=YPos.TOP)
        if value_colour:
            self.set_text_color(*value_colour)
        self.set_font("Helvetica", "B", 9)
        self.cell(0, 6, value, fill=fill,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*C_TEXT)

    def coloured_badge(self, label: str, colour: tuple, x: float):
        self.set_x(x)
        self.set_fill_color(*colour)
        self.set_text_color(*C_WHITE)
        self.set_font("Helvetica", "B", 8)
        self.cell(38, 6, f"  {label}", fill=True,
                  new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_text_color(*C_TEXT)

    def embed_png(self, png_bytes: bytes, w: float = 180):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(png_bytes)
            tmp_path = tmp.name
        x = (210 - w) / 2
        self.image(tmp_path, x=x, w=w)
        Path(tmp_path).unlink(missing_ok=True)
        self.ln(3)


def build_pdf_report(
    results:        dict,
    stats:          dict,
    flags:          dict,
    mean_hdop:      float,
    mean_pdop:      float,
    ref_lat:        float,
    ref_lon:        float,
    ref_h:          float,
    obs_filename:   str = "",
    nav_filename:   str = "",
    fig_scatter:    Optional[plt.Figure] = None,
    fig_snr:        Optional[plt.Figure] = None,
    fig_timeseries: Optional[plt.Figure] = None,
) -> bytes:
    """
    Build a complete PDF report and return it as bytes.
    Returns raw PDF bytes suitable for st.download_button().
    """
    pdf = GNSSReport(obs_filename=obs_filename, nav_filename=nav_filename)
    pdf.add_page()

    # Title block
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*C_DARK)
    pdf.ln(2)
    pdf.cell(0, 10, "GNSS Positioning Quality Report",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*C_MID_GREY)
    pdf.cell(0, 5,
             "Single Point Positioning (SPP) Analysis  |  "
             f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_text_color(*C_TEXT)
    pdf.ln(4)

    # Section 1 - Session overview
    pdf.section_title("1. Session Overview")

    rinex_ver   = results.get("rinex_version", "Unknown")
    n_sats      = str(results.get("n_sats_total", "-"))
    n_processed = results.get("n_processed", 0)
    interval    = results.get("epoch_interval_seconds", 30.0)
    was_cleaned = results.get("obs_was_cleaned", False)

    rows = [
        ("Observation file",       obs_filename or "-"),
        ("Navigation file",        nav_filename or "-"),
        ("RINEX format",           rinex_ver),
        ("File preprocessed",      "Yes - RINEX cleaner applied" if was_cleaned else "No"),
        ("Epoch interval",         f"{interval:.0f} second(s)"),
        ("Epochs processed",       str(n_processed)),
        ("GPS satellites in file", n_sats),
        ("Session duration",       f"{n_processed * interval / 60:.1f} minutes"),
    ]
    for i, (k, v) in enumerate(rows):
        pdf.kv_row(k, v, fill=(i % 2 == 0))

    # Section 2 - Reference coordinates
    pdf.section_title("2. Reference Receiver Coordinates")
    coord_rows = [
        ("Latitude",           f"{ref_lat:.6f} deg N"),
        ("Longitude",          f"{ref_lon:.6f} deg"),
        ("Ellipsoidal height", f"{ref_h:.3f} m"),
        ("Coordinate system",  "WGS84 / ITRF"),
    ]
    for i, (k, v) in enumerate(coord_rows):
        pdf.kv_row(k, v, fill=(i % 2 == 0))

    # Section 3 - Accuracy metrics
    pdf.section_title("3. Positioning Accuracy")

    cep50  = stats.get("CEP50",  float("nan"))
    cep95  = stats.get("CEP95",  float("nan"))
    rmse_h = stats.get("RMSE_H", float("nan"))
    rmse_v = stats.get("RMSE_V", float("nan"))
    drms2  = stats.get("2DRMS",  float("nan"))
    mean_h = stats.get("mean_H", float("nan"))

    acc_rows = [
        ("CEP50 - median horizontal error",  f"{cep50:.1f} m",  _cep50_colour(cep50)),
        ("CEP95 - 95th percentile horiz.",   f"{cep95:.1f} m",  _cep50_colour(cep95)),
        ("RMSE horizontal",                  f"{rmse_h:.1f} m", None),
        ("RMSE vertical",                    f"{rmse_v:.1f} m", None),
        ("2DRMS",                            f"{drms2:.1f} m",  None),
        ("Mean horizontal error",            f"{mean_h:.1f} m", None),
        ("Mean HDOP",                        f"{mean_hdop:.2f}", _hdop_colour(mean_hdop)),
        ("Mean PDOP",                        f"{mean_pdop:.2f}", None),
    ]
    for i, (k, v, col) in enumerate(acc_rows):
        pdf.kv_row(k, v, fill=(i % 2 == 0), value_colour=col)

    # Section 4 - Signal quality summary
    pdf.section_title("4. Signal Quality Summary")

    n_clean     = sum(1 for f in flags.values() if f == "clean")
    n_suspect   = sum(1 for f in flags.values() if f == "suspect")
    n_multipath = sum(1 for f in flags.values() if f == "multipath")
    total_sats  = n_clean + n_suspect + n_multipath

    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6,
             f"  {total_sats} GPS satellites assessed:   "
             f"{n_clean} clean   |   "
             f"{n_suspect} suspect   |   "
             f"{n_multipath} multipath",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    pdf.coloured_badge(f"+ {n_clean} Clean",         C_GREEN, x=15)
    pdf.coloured_badge(f"! {n_suspect} Suspect",      C_AMBER, x=58)
    pdf.coloured_badge(f"x {n_multipath} Multipath",  C_RED,   x=101)
    pdf.ln(10)

    # Section 5 - Per-satellite table
    pdf.section_title("5. Per-Satellite Quality Table")

    snr_results = results.get("snr_results", {})
    cmc_results = results.get("cmc_results", {})

    pdf.set_fill_color(*C_DARK)
    pdf.set_text_color(*C_WHITE)
    pdf.set_font("Helvetica", "B", 8)
    col_w   = [20, 26, 30, 28, 30, 26]
    headers = ["Satellite", "Flag", "Mean SNR", "SNR flag",
               "CMC std (m)", "CMC flag"]
    for w, h in zip(col_w, headers):
        pdf.cell(w, 6, f" {h}", fill=True,
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.ln(6)
    pdf.set_text_color(*C_TEXT)

    for i, sat in enumerate(sorted(flags.keys())):
        flag     = flags[sat]
        snr_r    = snr_results.get(sat, {}).get("result", {})
        cmc_r    = cmc_results.get(sat, {}).get("result", {})
        mean_snr = snr_r.get("mean_snr", None)
        cmc_std  = cmc_r.get("std", None)
        snr_flag = snr_r.get("flag", "-")
        cmc_flag = cmc_r.get("flag", "-")

        snr_str = f"{mean_snr:.1f} dB-Hz" if mean_snr else "-"
        cmc_str = f"{cmc_std:.4f}" if cmc_std else "-"

        row_fill = (i % 2 == 0)
        pdf.set_fill_color(*C_LIGHT_GREY)

        row_data = [sat, flag.capitalize(), snr_str,
                    snr_flag.capitalize(), cmc_str, cmc_flag.capitalize()]

        for j, (w, val) in enumerate(zip(col_w, row_data)):
            if j == 1:
                pdf.set_text_color(*_flag_colour(flag))
                pdf.set_font("Helvetica", "B", 8)
            else:
                pdf.set_text_color(*C_TEXT)
                pdf.set_font("Helvetica", "", 8)
            pdf.cell(w, 5, f" {val}", fill=row_fill,
                     new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.ln(5)

    pdf.set_text_color(*C_TEXT)

    # Section 6 - Position scatter plot
    if fig_scatter is not None:
        pdf.add_page()
        pdf.section_title("6. Position Scatter Plot")
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*C_MID_GREY)
        pdf.cell(0, 5,
                 "Each dot = one GPS position fix. "
                 "Red cross = true location. "
                 "Green circle = CEP50 radius.",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*C_TEXT)
        pdf.ln(2)
        pdf.embed_png(_fig_to_png_bytes(fig_scatter), w=140)

    # Section 7 - SNR heatmap
    if fig_snr is not None:
        pdf.section_title("7. Signal Strength Heatmap (SNR)")
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*C_MID_GREY)
        pdf.cell(0, 5,
                 "Green = strong signal (>45 dB-Hz). "
                 "Red = weak (<25 dB-Hz). "
                 "White = satellite below horizon.",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*C_TEXT)
        pdf.ln(2)
        pdf.embed_png(_fig_to_png_bytes(fig_snr), w=175)

    # Section 8 - Error time series
    if fig_timeseries is not None:
        pdf.add_page()
        pdf.section_title("8. Error and DOP Time Series")
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*C_MID_GREY)
        pdf.cell(0, 5,
                 "Top: horizontal distance from true location at each epoch. "
                 "Middle: vertical error. "
                 "Bottom: HDOP geometry score.",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*C_TEXT)
        pdf.ln(2)
        pdf.embed_png(_fig_to_png_bytes(fig_timeseries), w=175)

    # Section 9 - Interpretation
    pdf.add_page()
    pdf.section_title("9. Plain-English Interpretation")

    if cep50 < 20:
        acc_interp = (
            f"The session achieved excellent horizontal accuracy with a CEP50 of "
            f"{cep50:.1f} m. This is near the upper limit of what single-frequency "
            f"SPP can achieve under ideal conditions."
        )
    elif cep50 < 60:
        acc_interp = (
            f"The session achieved good horizontal accuracy with a CEP50 of "
            f"{cep50:.1f} m. This is consistent with expected SPP performance "
            f"under normal ionospheric conditions."
        )
    elif cep50 < 150:
        acc_interp = (
            f"The session achieved moderate horizontal accuracy with a CEP50 of "
            f"{cep50:.1f} m. This may reflect degraded satellite geometry, "
            f"ionospheric activity, or multipath contamination."
        )
    else:
        acc_interp = (
            f"The session showed poor horizontal accuracy with a CEP50 of "
            f"{cep50:.1f} m. Check that the reference coordinates are correct "
            f"and that the navigation file matches the observation date."
        )

    if mean_hdop < 1.5:
        geom_interp = (
            "Satellite geometry was excellent throughout the session "
            f"(mean HDOP {mean_hdop:.2f}, below 1.5 threshold)."
        )
    elif mean_hdop < 2.0:
        geom_interp = (
            f"Satellite geometry was good (mean HDOP {mean_hdop:.2f}, "
            "within the 1.5 to 2.0 acceptable range)."
        )
    else:
        geom_interp = (
            f"Satellite geometry was marginal (mean HDOP {mean_hdop:.2f}, "
            "above the 2.0 threshold), which may have contributed to "
            "reduced accuracy."
        )

    if n_multipath > 0:
        sig_interp = (
            f"{n_multipath} satellite(s) showed evidence of signal reflection "
            f"(multipath) and were heavily downweighted in the position solution."
        )
    elif n_suspect > 0 and total_sats > 0 and n_suspect > total_sats / 2:
        sig_interp = (
            "More than half the satellites were flagged as suspect, "
            "indicating short tracking arcs, weak signals, or minor multipath."
        )
    else:
        sig_interp = (
            f"{n_clean} of {total_sats} satellites were rated clean with "
            "reliable signal quality throughout the session."
        )

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*C_TEXT)
    for para in [acc_interp, geom_interp, sig_interp]:
        pdf.multi_cell(0, 5, para)
        pdf.ln(2)

    # Section 10 - Limitations
    pdf.section_title("10. Limitations and Disclaimers")

    limitations = [
        (
            "This software implements Single Point Positioning (SPP) using "
            "single-frequency GPS broadcast ephemerides. Achievable accuracy "
            "is 5 to 100 m horizontal depending on conditions. It is not "
            "suitable for cadastral, construction, or precision surveys."
        ),
        (
            "Accuracy statistics are computed relative to the reference "
            "coordinates entered by the user. Results are only meaningful if "
            "the reference coordinates are the true, surveyed position of the "
            "GPS antenna phase centre."
        ),
        (
            "The Klobuchar ionospheric model corrects approximately 50% of "
            "ionospheric delay on average. Residual ionospheric error is the "
            "dominant error source in most sessions."
        ),
        (
            "This software is developed for educational and research purposes "
            "at the Department of Geodesy and Geomatics Engineering, "
            "University of New Brunswick. It has not been certified for "
            "operational or commercial use."
        ),
        (
            "Navigation file coverage must match the observation session date "
            "and location. Using a navigation file from a different date will "
            "produce incorrect satellite positions and meaningless accuracy "
            "results."
        ),
    ]

    for i, para in enumerate(limitations, 1):
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(6, 5, f"{i}.", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, para)
        pdf.ln(1)

    return bytes(pdf.output())

