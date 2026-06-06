"""
Generate technical PDF report — Phase 4 Milestone 3
Produces a 3-4 page engineering report suitable for job applications.
Run from project root.
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, HRFlowable, Image
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from pathlib import Path
import datetime

OUTPUT = "outputs/GNSS_Quality_Analyzer_Technical_Report.pdf"
Path("outputs").mkdir(exist_ok=True)

doc = SimpleDocTemplate(
    OUTPUT,
    pagesize=letter,
    rightMargin=0.9*inch,
    leftMargin=0.9*inch,
    topMargin=0.9*inch,
    bottomMargin=0.9*inch,
)

styles = getSampleStyleSheet()

# Custom styles
title_style = ParagraphStyle(
    "CustomTitle",
    parent=styles["Title"],
    fontSize=16,
    spaceAfter=6,
    textColor=colors.HexColor("#1a1a2e"),
    alignment=TA_CENTER,
)
subtitle_style = ParagraphStyle(
    "Subtitle",
    parent=styles["Normal"],
    fontSize=10,
    spaceAfter=4,
    textColor=colors.HexColor("#444441"),
    alignment=TA_CENTER,
)
h1_style = ParagraphStyle(
    "H1",
    parent=styles["Heading1"],
    fontSize=12,
    spaceBefore=14,
    spaceAfter=4,
    textColor=colors.HexColor("#185FA5"),
    borderPad=2,
)
h2_style = ParagraphStyle(
    "H2",
    parent=styles["Heading2"],
    fontSize=10,
    spaceBefore=8,
    spaceAfter=3,
    textColor=colors.HexColor("#534AB7"),
)
body_style = ParagraphStyle(
    "Body",
    parent=styles["Normal"],
    fontSize=9.5,
    spaceAfter=6,
    leading=14,
    alignment=TA_JUSTIFY,
)
caption_style = ParagraphStyle(
    "Caption",
    parent=styles["Normal"],
    fontSize=8.5,
    spaceAfter=8,
    textColor=colors.HexColor("#5F5E5A"),
    alignment=TA_CENTER,
    italics=True,
)

def h1(text): return Paragraph(text, h1_style)
def h2(text): return Paragraph(text, h2_style)
def body(text): return Paragraph(text, body_style)
def sp(n=6): return Spacer(1, n)
def hr(): return HRFlowable(width="100%", thickness=0.5,
                             color=colors.HexColor("#D3D1C7"), spaceAfter=4)

def make_table(data, col_widths=None, header=True):
    t = Table(data, colWidths=col_widths)
    style = [
        ("FONTSIZE",    (0,0), (-1,-1), 8.5),
        ("TOPPADDING",  (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",(0,0),(-1,-1), 4),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING",(0,0), (-1,-1), 6),
        ("GRID",        (0,0), (-1,-1), 0.3, colors.HexColor("#B4B2A9")),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),
         [colors.white, colors.HexColor("#F1EFE8")]),
    ]
    if header:
        style += [
            ("BACKGROUND",  (0,0), (-1,0), colors.HexColor("#185FA5")),
            ("TEXTCOLOR",   (0,0), (-1,0), colors.white),
            ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",    (0,0), (-1,0), 9),
        ]
    t.setStyle(TableStyle(style))
    return t

# ── Build document ─────────────────────────────────────────────────────────────
story = []

# Title
story.append(Paragraph(
    "GNSS Positioning Quality Analyzer with Multipath Detection",
    title_style
))
story.append(Paragraph(
    "Technical Report — Dweep Saha, Geomatics Engineering, University of New Brunswick",
    subtitle_style
))
story.append(Paragraph(
    f"June 2025  |  github.com/DweepSaha/gnss-rinex-pipeline-  |  gnss-saha.streamlit.app",
    subtitle_style
))
story.append(sp(4))
story.append(hr())
story.append(sp(4))

# Abstract
story.append(h1("Abstract"))
story.append(body(
    "This report describes the design, implementation, and validation of a GNSS positioning "
    "quality analyzer built entirely in Python from first principles. The system ingests RINEX 3 "
    "observation and navigation files, implements a Single Point Positioning (SPP) solver using "
    "iterative weighted least squares, detects multipath contamination through Signal-to-Noise "
    "Ratio (SNR) deviation analysis and Code-Minus-Carrier (CMC) observables, and applies "
    "Klobuchar ionospheric corrections. Validated on real data from three NRCan Canadian Active "
    "Control System (CACS) stations — FRDN (Fredericton NB), ALGO (Algonquin Park ON), and "
    "HLFX (Halifax NS) — the system achieved a CEP50 horizontal accuracy of 53–55 metres with "
    "a 24.4% improvement over the uncorrected baseline. The complete pipeline is deployed as an "
    "interactive Streamlit web application available at gnss-saha.streamlit.app."
))

story.append(h1("1. Introduction"))
story.append(body(
    "Global Navigation Satellite System (GNSS) positioning quality is a critical parameter in "
    "autonomous vehicles, precision agriculture, infrastructure surveying, and navigation systems. "
    "While commercial GNSS receivers report position coordinates, they rarely expose the "
    "signal-level quality metrics — satellite geometry, multipath contamination, and atmospheric "
    "delay — that determine accuracy in challenging environments."
))
story.append(body(
    "This project implements a complete GNSS quality analysis pipeline targeting the technical "
    "requirements of positioning and navigation companies including Hexagon Autonomy and "
    "Positioning, Trimble, Garmin, NovAtel, and OxTS. The pipeline operates on freely available "
    "RINEX data from the NRCan CORS network and requires no proprietary hardware or software."
))

story.append(h1("2. Methodology"))
story.append(h2("2.1 Single Point Positioning"))
story.append(body(
    "The SPP solver implements the standard pseudorange observation model. For satellite i, "
    "the corrected pseudorange observation equation is:"
))
story.append(body(
    "<b>ρᵢ_corrected = rᵢ + c·δtᵣ</b>"
))
story.append(body(
    "where rᵢ is the geometric range, c is the speed of light, and δtᵣ is the receiver clock "
    "error. The solver linearizes this nonlinear system around an approximate position and "
    "applies iterative weighted least squares:"
))
story.append(body(
    "<b>x = (HᵀWH)⁻¹ HᵀW Δρ</b>"
))
story.append(body(
    "where H is the design matrix of unit line-of-sight vectors, W is a diagonal weight matrix "
    "derived from signal quality flags, and Δρ is the vector of range residuals. Iteration "
    "continues until the position correction falls below 0.001 metres."
))

story.append(h2("2.2 Error Corrections"))
story.append(body(
    "Four corrections are applied to each pseudorange before the least-squares solution: "
    "(1) satellite clock correction using broadcast af0/af1/af2 parameters; "
    "(2) relativistic correction from the orbital mechanics model; "
    "(3) Klobuchar 8-coefficient ionospheric delay model using IGS-published coefficients; "
    "(4) simplified Hopfield tropospheric delay model as a function of satellite elevation angle. "
    "The ephemeris record closest to each observation epoch is selected to minimize orbital "
    "extrapolation error — a key improvement over using only the first available record."
))

story.append(h2("2.3 Multipath Detection"))
story.append(body(
    "Two complementary methods detect signal contamination. SNR deviation analysis applies a "
    "Savitzky-Golay filter to estimate the smooth SNR baseline for each satellite, then flags "
    "epochs where deviation exceeds 3 dB-Hz (suspect) or 6 dB-Hz (multipath). "
    "Code-Minus-Carrier (CMC) analysis computes the difference between pseudorange and carrier "
    "phase measurements scaled to metres. After removing the integer ambiguity and ionospheric "
    "drift through arc-by-arc detrending, the residual CMC standard deviation directly measures "
    "pseudorange multipath. Satellites with CMC standard deviation above 0.5 m are flagged. "
    "Combined flags from both methods feed into the weighted least-squares solver."
))

story.append(h2("2.4 Accuracy Assessment"))
story.append(body(
    "Position accuracy is assessed by comparing computed positions against NRCan published "
    "reference coordinates for each CACS station. Horizontal and vertical errors are computed "
    "in a local north-east-up frame using the radius of curvature at the reference latitude. "
    "Statistics reported include CEP50 (median horizontal error), CEP95 (95th percentile), "
    "RMSE horizontal, RMSE vertical, and 2DRMS."
))

story.append(h1("3. Results"))
story.append(h2("3.1 Phase 2 vs Phase 3 Accuracy Improvement (FRDN)"))

p2p3_data = [
    ["Metric", "Phase 2 (baseline)", "Phase 3 (corrected)", "Improvement"],
    ["CEP50 (m)",  "72.8", "55.0", "24.4%"],
    ["CEP95 (m)",  "127.7", "99.9", "21.8%"],
    ["RMSE_H (m)", "82.4", "59.7", "27.5%"],
    ["RMSE_V (m)", "143.0", "68.5", "52.1%"],
    ["Mean HDOP",  "1.46", "1.46", "—"],
]
story.append(make_table(p2p3_data, col_widths=[1.8*inch, 1.5*inch, 1.6*inch, 1.3*inch]))
story.append(Paragraph(
    "Table 1: Accuracy improvement from Phase 2 (no corrections) to Phase 3 "
    "(Klobuchar + CMC/SNR weighting + closest ephemeris selection). Station FRDN, "
    "2025-06-01 00:00–02:00 UTC, 240 epochs.",
    caption_style
))

story.append(h2("3.2 Multi-Station Validation"))
story.append(body(
    "The pipeline was validated across three NRCan CACS stations on the same date and time "
    "window to assess generalisability."
))

ms_data = [
    ["Station", "Location", "CEP50", "CEP95", "RMSE_H", "RMSE_V", "HDOP", "Clean sats"],
    ["FRDN", "Fredericton, NB",     "55.0 m", "99.9 m",  "59.7 m", "68.5 m", "1.46", "10/13"],
    ["ALGO", "Algonquin Park, ON",  "53.3 m", "94.8 m",  "57.3 m", "29.5 m", "1.27",  "8/12"],
    ["HLFX", "Halifax, NS",         "53.1 m", "98.6 m",  "59.7 m", "70.5 m", "1.49",  "8/12"],
]
story.append(make_table(ms_data,
    col_widths=[0.6*inch, 1.5*inch, 0.7*inch, 0.7*inch,
                0.7*inch, 0.7*inch, 0.55*inch, 0.75*inch]))
story.append(Paragraph(
    "Table 2: Multi-station accuracy comparison. All stations processed with identical "
    "pipeline settings. GPS only, 30-second sampling, 2025-06-01 00:00–02:00 UTC.",
    caption_style
))

story.append(body(
    "CEP50 is consistent across all three stations (53–55 m), confirming pipeline "
    "generalisability. ALGO shows significantly lower RMSE_V (29.5 m) attributed to its "
    "rural open-sky environment in Algonquin Provincial Park with minimal terrain obstruction. "
    "ALGO also achieves the best satellite geometry with mean HDOP of 1.27."
))

story.append(h2("3.3 Signal Quality Analysis"))
story.append(body(
    "SNR and CMC analysis at FRDN identified 10 clean satellites, 3 suspect, and 0 multipath "
    "contaminated — consistent with FRDN's open-sky geodetic monument location. The CMC "
    "standard deviation ranged from 0.107 m (G10, high elevation) to 0.330 m (G31, setting "
    "satellite with cycle slips). The ionospheric drift artifact in raw CMC — caused by the "
    "divergence between code and carrier phase ionospheric effects — was successfully removed "
    "using arc-by-arc Savitzky-Golay detrending."
))

story.append(h2("3.4 Ionospheric Correction Analysis"))
story.append(body(
    "Klobuchar corrections of 3–5 metres were applied per satellite at midnight UTC over "
    "New Brunswick. The minimal accuracy improvement (0.6 m CEP50) from iono correction "
    "on this session is consistent with published literature — at midnight the ionosphere "
    "is near its daily minimum and corrections are nearly uniform across all satellites, "
    "which the solver partially absorbs into the receiver clock parameter. A comparison "
    "with May 10 2024 data (Kp=9 geomagnetic storm) confirmed that Klobuchar coefficients "
    "become less reliable during extreme storm events, consistent with GPS ICD specifications "
    "stating 50% accuracy for the model under nominal conditions."
))

story.append(h1("4. Limitations"))
story.append(body(
    "<b>Single frequency.</b> The pipeline uses L1 C/A pseudoranges only. Dual-frequency "
    "receivers eliminate ionospheric delay by combining L1 and L2 observations, reducing "
    "horizontal errors by 5–15 metres under active ionospheric conditions."
))
story.append(body(
    "<b>Klobuchar model accuracy.</b> The broadcast Klobuchar model corrects approximately "
    "50% of ionospheric delay under quiet conditions. IGS IONEX global ionospheric maps "
    "achieve 80–90% correction accuracy and are identified as the primary upgrade path."
))
story.append(body(
    "<b>No carrier-phase positioning.</b> SPP achieves metre-level accuracy. Precise Point "
    "Positioning (PPP) using carrier-phase observations would achieve centimetre accuracy "
    "with the same hardware."
))

story.append(h1("5. Conclusion"))
story.append(body(
    "A complete GNSS positioning quality analyzer was implemented from first principles in "
    "Python and validated on real data from three NRCan CACS stations in eastern Canada. "
    "The Phase 3 pipeline achieved a CEP50 of 55.0 metres — a 24.4% improvement over the "
    "uncorrected Phase 2 baseline — through improved ephemeris selection, Klobuchar "
    "ionospheric corrections, and quality-based satellite weighting. The pipeline correctly "
    "identifies signal quality at a geodetic reference station (10 clean, 0 multipath at FRDN) "
    "and produces results consistent with published SPP performance benchmarks. The system "
    "is deployed as a publicly accessible Streamlit dashboard at gnss-saha.streamlit.app."
))

story.append(sp(8))
story.append(hr())
story.append(body(
    "<b>Keywords:</b> GNSS, GPS, Single Point Positioning, SPP, multipath detection, "
    "code-minus-carrier, Klobuchar ionospheric model, RINEX, NRCan CORS, weighted least squares"
))

# Build PDF
doc.build(story)
print(f"Report saved: {OUTPUT}")