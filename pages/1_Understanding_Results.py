"""
Understanding Your Results — help and glossary page.
Accessible from the sidebar navigation in the Streamlit multi-page app.
"""
import streamlit as st

st.set_page_config(
    page_title="Understanding Your Results",
    page_icon="📖",
    layout="wide",
)

st.title("📖 Understanding Your Results")
st.caption(
    "A plain-English guide to every input, output, and quality metric "
    "in the GNSS Positioning Quality Analyzer."
)

st.divider()

# ── What did this software do? ─────────────────────────────────────────────
st.header("What did this software do?")
st.markdown("""
GPS satellites broadcast radio signals continuously from about 20,000 km above Earth.
Your GPS receiver records the time it takes each signal to arrive, which tells it how
far away each satellite is. With measurements from at least four satellites, the receiver
can compute its position using geometry — the same principle as triangulation.

This software reads those raw measurements, applies corrections for satellite clock errors,
atmospheric delays, and signal reflections, then computes your position for every observation
in the session. It compares those computed positions against the known true location to
measure how accurate the session was, and it analyses the signal quality of each satellite
to identify potential problems.

The result is a complete quality report: how accurate were the positions, which satellites
were reliable, and what might have caused any degradation in accuracy.
""")

st.divider()

# ── Inputs ─────────────────────────────────────────────────────────────────
st.header("Your inputs explained")

with st.expander("GPS measurement file (RINEX observation file)", expanded=False):
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("**Technical name:** RINEX 3 observation file")
        st.markdown("**File extension:** `.rnx`, `.obs`, `.25o`")
        st.markdown("**Typical size:** 5–30 MB for a full day")
        st.markdown("**Where to get it:**")
        st.markdown(
            "- NRCan CORS network: [webapp.csrs-scrs.nrcan.gc.ca]"
            "(https://webapp.csrs-scrs.nrcan.gc.ca/geod/data-donnees/cacs-scca.php)"
        )
        st.markdown("- Export from Trimble Business Center or Leica Infinity")
        st.markdown("- Download from IGS network stations worldwide")
    with col2:
        st.info(
            "**Plain English:** This is the recording of everything your GPS receiver "
            "measured during the session. Every 30 seconds it wrote down:\n\n"
            "- The distance to each satellite (pseudorange)\n"
            "- The phase of the carrier wave (carrier phase)\n"
            "- The signal strength from each satellite (SNR)\n\n"
            "Think of it like the raw data file from a scientific instrument — "
            "all the measurements before any processing."
        )

with st.expander("Satellite orbit file (RINEX navigation file)", expanded=False):
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("**Technical name:** RINEX 3 navigation file")
        st.markdown("**File extension:** `.rnx`, `.25n`")
        st.markdown("**Typical size:** 0.5–2 MB")
        st.markdown("**Coverage:** One file covers the full day for all stations")
        st.markdown("**Where to get it:**")
        st.markdown(
            "- Same NRCan page as the observation file — select navigation file type"
        )
    with col2:
        st.info(
            "**Plain English:** This file describes where every GPS satellite was in space "
            "throughout the day, using mathematical orbital parameters called Keplerian elements.\n\n"
            "Without this file the software cannot calculate satellite positions, "
            "so it cannot compute your position.\n\n"
            "You only need one navigation file per day — it works for any receiver "
            "location because satellite orbits are the same from anywhere on Earth."
        )

with st.expander("Reference coordinates (known true position)", expanded=False):
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("**Latitude:** Decimal degrees, positive = North")
        st.markdown("**Longitude:** Decimal degrees, negative = West")
        st.markdown("**Height:** Ellipsoidal height in metres — not elevation above sea level")
        st.markdown("**Example (Fredericton FRDN):**")
        st.code("Latitude:  45.933497\nLongitude: -66.659879\nHeight:    95.960 m")
        st.markdown("**Where to get it:**")
        st.markdown("- NRCan CORS coordinate database")
        st.markdown("- Control point database for your jurisdiction")
        st.markdown("- IGS station information page")
    with col2:
        st.info(
            "**Plain English:** This is the known answer — the true location of your GPS receiver.\n\n"
            "The software computes where the receiver was based on the GPS measurements, "
            "then compares that to where it actually was. The difference is your positioning error.\n\n"
            "**Important note on height:** The height you enter must be the ellipsoidal height, "
            "not the elevation above sea level. These differ by 10–50 metres depending on location "
            "because the Earth is not a perfect sphere. NRCan published coordinates always give "
            "ellipsoidal height."
        )

with st.expander("Observations to analyze (epoch count)", expanded=False):
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("**What is an epoch?**")
        st.markdown(
            "One epoch = one complete set of measurements from all visible satellites. "
            "At 30-second sampling, there are 2 epochs per minute and 2880 epochs in a full day."
        )
        st.markdown("**Conversion table:**")
        st.markdown("""
| Epochs | Duration |
|---|---|
| 10 | 5 minutes |
| 30 | 15 minutes |
| 60 | 30 minutes |
| 120 | 1 hour |
| 240 | 2 hours |
| 480 | 4 hours |
""")
    with col2:
        st.info(
            "**Plain English:** This controls how much of your GPS session is analyzed.\n\n"
            "More epochs = more reliable statistics but longer processing time.\n\n"
            "For a quick quality check, use 60 epochs (30 minutes). "
            "For a full session report, use 120–240 epochs."
        )

st.divider()

# ── Accuracy metrics ────────────────────────────────────────────────────────
st.header("Reading your accuracy results")

with st.expander("CEP50 — Circular Error Probable (50%)", expanded=True):
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("**Technical definition:**")
        st.markdown(
            "The radius of a circle, centred on the true position, that contains "
            "50% of all computed position fixes. Equivalent to the median horizontal error."
        )
        st.markdown("**Formula:** 50th percentile of all horizontal errors")
        st.markdown("**Units:** Metres")
        st.markdown("**Industry benchmark values:**")
        st.markdown("""
| CEP50 | Accuracy class |
|---|---|
| < 1 m | RTK / PPP — professional survey |
| 1–5 m | SBAS corrected |
| 5–20 m | SBAS or good autonomous GPS |
| 20–100 m | Standard autonomous GPS (SPP) |
| > 100 m | Degraded — investigate cause |
""")
    with col2:
        st.success(
            "**Plain English:** If your CEP50 is 55 metres, it means that if you were "
            "standing on the true location and drew a circle of radius 55 m around yourself, "
            "half of all the positions your GPS computed would fall inside that circle.\n\n"
            "It is the most commonly used single number to describe GPS accuracy. "
            "Smaller is always better.\n\n"
            "**Why 50%?** Because GPS errors are random — some positions will be closer "
            "to the truth, some further away. CEP50 tells you the typical error, "
            "not the worst case."
        )

with st.expander("CEP95 — Circular Error Probable (95%)", expanded=False):
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("**Technical definition:**")
        st.markdown(
            "The radius of a circle containing 95% of all computed position fixes. "
            "A more conservative accuracy estimate that captures most outliers."
        )
        st.markdown("**Typical ratio:** CEP95 ≈ 2.0 × CEP50 for GPS errors")
    with col2:
        st.info(
            "**Plain English:** The worst-case accuracy you would expect 95% of the time. "
            "If CEP95 is 100 m, then in 19 out of 20 observations the position was "
            "within 100 m of the truth. Only 1 in 20 observations was worse than this.\n\n"
            "Use CEP95 when you need to guarantee accuracy for a specific application."
        )

with st.expander("RMSE — Root Mean Square Error", expanded=False):
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("**Technical definition:**")
        st.markdown(
            "The square root of the mean of squared errors. "
            "Computed separately for horizontal (RMSE_H) and vertical (RMSE_V) components."
        )
        st.markdown("**Formula:** √(mean of all errors²)")
        st.markdown(
            "**Why it differs from CEP50:** RMSE penalizes large outliers more heavily "
            "than the median. If you have a few very large errors, RMSE will be "
            "larger than CEP50."
        )
    with col2:
        st.info(
            "**Plain English:** The average positioning error, but calculated in a way "
            "that gives extra weight to large errors.\n\n"
            "RMSE_H = average horizontal error\n"
            "RMSE_V = average vertical (height) error\n\n"
            "Vertical error is almost always larger than horizontal error in GPS "
            "because satellites are only above the horizon — you never have a satellite "
            "directly below you to anchor the vertical measurement."
        )

with st.expander("HDOP — Horizontal Dilution of Precision", expanded=False):
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("**Technical definition:**")
        st.markdown(
            "A dimensionless number derived from the satellite geometry matrix "
            "that describes how satellite positions amplify or reduce ranging errors "
            "in the horizontal plane."
        )
        st.markdown("**HDOP scale:**")
        st.markdown("""
| HDOP | Geometry quality |
|---|---|
| < 1.0 | Ideal |
| 1.0–1.5 | Excellent |
| 1.5–2.0 | Good |
| 2.0–3.0 | Moderate |
| 3.0–5.0 | Fair |
| > 5.0 | Poor — avoid survey work |
""")
    with col2:
        st.info(
            "**Plain English:** A score that describes how well-spread the GPS satellites "
            "were across the sky during your session.\n\n"
            "Imagine four satellites all clustered in the northeast sky — their lines "
            "of position would all point in roughly the same direction, making it hard "
            "to pinpoint your exact location. This gives a high HDOP.\n\n"
            "Now imagine four satellites spread evenly around the sky — their lines "
            "of position cross at sharp angles, giving a precise intersection. "
            "This gives a low HDOP.\n\n"
            "HDOP changes throughout the day as satellites move across the sky."
        )

with st.expander("PDOP — Position Dilution of Precision", expanded=False):
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("**Technical definition:**")
        st.markdown(
            "Same as HDOP but includes the vertical dimension. "
            "PDOP² = HDOP² + VDOP² where VDOP is the vertical component."
        )
        st.markdown("**Typical values:** PDOP is always larger than HDOP")
        st.markdown("**Good PDOP:** Under 2.5")
    with col2:
        st.info(
            "**Plain English:** The same geometry score as HDOP but measuring all three "
            "dimensions — north, east, and up.\n\n"
            "Since GPS satellites are always above the horizon, the vertical geometry "
            "is always weaker than horizontal, so PDOP is always larger than HDOP."
        )

st.divider()

# ── Signal quality ──────────────────────────────────────────────────────────
st.header("Reading your signal quality")

with st.expander("SNR — Signal-to-Noise Ratio", expanded=False):
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("**Technical definition:**")
        st.markdown(
            "The ratio of the GPS signal power to the background noise power, "
            "expressed in decibel-Hertz (dB-Hz)."
        )
        st.markdown("**Typical values:**")
        st.markdown("""
| SNR | Signal quality |
|---|---|
| > 45 dB-Hz | Excellent — high elevation satellite |
| 35–45 dB-Hz | Good — normal operation |
| 25–35 dB-Hz | Weak — low elevation or obstruction |
| < 25 dB-Hz | Very weak — likely blocked |
""")
    with col2:
        st.info(
            "**Plain English:** How strong the satellite signal is compared to background noise. "
            "Like tuning a radio — a strong station has high SNR, a weak or static-filled "
            "station has low SNR.\n\n"
            "Higher satellites have stronger signals because their signal travels through "
            "less atmosphere. Low-elevation satellites near the horizon have weaker signals "
            "because the signal passes through more atmosphere to reach you.\n\n"
            "In the SNR heatmap, green = strong signal, red = weak signal."
        )

with st.expander("Multipath — Signal Reflection", expanded=False):
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("**Technical definition:**")
        st.markdown(
            "Multipath occurs when a GPS signal reaches the receiver via two or more paths — "
            "the direct path from the satellite and one or more reflected paths off buildings, "
            "terrain, or other surfaces. The reflected signal arrives slightly later than the "
            "direct signal, causing a pseudorange error."
        )
        st.markdown("**Effect on accuracy:** Can introduce errors of 1–100 metres")
        st.markdown("**Detection method:** Code-Minus-Carrier (CMC) analysis")
    with col2:
        st.warning(
            "**Plain English:** Like an echo corrupting a sound recording.\n\n"
            "The GPS receiver measures distance by timing how long the signal takes to arrive. "
            "If the signal bounces off a building before reaching the receiver, "
            "it has traveled a longer path — so the receiver thinks the satellite is "
            "further away than it actually is. This creates a positioning error.\n\n"
            "Multipath is most common near buildings, walls, vehicles, and water surfaces. "
            "It is worst for low-elevation satellites whose signals arrive at shallow angles.\n\n"
            "**How to reduce it:** Use a choke-ring antenna, avoid placing the receiver "
            "near reflective surfaces, and use an elevation mask above 10–15 degrees."
        )

with st.expander("CMC std — Code-Minus-Carrier standard deviation", expanded=False):
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("**Technical definition:**")
        st.markdown(
            "The standard deviation of the code-minus-carrier (CMC) observable after "
            "removing the integer ambiguity and ionospheric drift. "
            "Measures the residual variation in the CMC time series which is "
            "primarily caused by pseudorange multipath."
        )
        st.markdown("**Thresholds:**")
        st.markdown("""
| CMC std | Flag |
|---|---|
| < 0.3 m | Clean |
| 0.3–0.5 m | Suspect |
| > 0.5 m | Multipath |
""")
    with col2:
        st.info(
            "**Plain English:** A number that measures how much the GPS code measurement "
            "is bouncing around compared to the carrier phase measurement.\n\n"
            "The carrier phase is very precise and stable. The pseudorange (code) is less "
            "precise and gets corrupted by multipath. By subtracting one from the other, "
            "we isolate the multipath contamination.\n\n"
            "A CMC std below 0.3 m means the code measurement is stable and reliable. "
            "Above 0.5 m means the code is oscillating — a strong sign of multipath."
        )

with st.expander("Clean / Suspect / Multipath flags", expanded=False):
    c1, c2, c3 = st.columns(3)
    with c1:
        st.success(
            "**✓ Clean**\n\n"
            "Signal strength is healthy (above 35 dB-Hz) and stable. "
            "No evidence of multipath. "
            "This satellite's measurements are fully trusted and given full weight "
            "in the position calculation."
        )
    with c2:
        st.warning(
            "**⚠ Suspect**\n\n"
            "Signal is either slightly weak, slightly oscillating, or the satellite "
            "only had a short tracking arc. "
            "May indicate low elevation, minor obstruction, or rising/setting satellite. "
            "Used with 30% weight in the position calculation."
        )
    with c3:
        st.error(
            "**✗ Multipath**\n\n"
            "Strong evidence of signal reflection detected by both SNR analysis "
            "and code-minus-carrier analysis. "
            "The measurement contains significant error from the reflected signal. "
            "Used with only 5% weight — nearly excluded from the position calculation."
        )

st.divider()

# ── Accuracy expectations ────────────────────────────────────────────────────
st.header("Accuracy expectations by application")
st.markdown("""
GPS positioning accuracy depends entirely on the technique used. This software implements
**Single Point Positioning (SPP)** — the fundamental GPS algorithm that uses one receiver
and broadcast satellite data. It is the technique used in smartphones and basic GPS receivers.

For higher accuracy, different techniques are required:
""")

col1, col2 = st.columns(2)
with col1:
    st.markdown("""
| Technique | Typical accuracy | How it works |
|---|---|---|
| **SPP** (this software) | 1–100 m | Single receiver, broadcast corrections |
| **SBAS** | 1–5 m | Adds satellite-based differential corrections |
| **DGNSS** | 0.5–3 m | Uses a nearby reference station |
| **RTK** | 0.01–0.05 m | Real-time carrier phase from reference station |
| **PPP** | 0.02–0.1 m | Precise satellite orbits and clocks |
""")

with col2:
    st.info(
        "**What SPP is good for:**\n\n"
        "- Reconnaissance and planning surveys\n"
        "- GIS data collection where metre-level accuracy is acceptable\n"
        "- Navigation and asset tracking\n"
        "- Quality checking of GNSS receiver performance\n"
        "- Signal quality analysis and multipath detection\n\n"
        "**What SPP is not suitable for:**\n\n"
        "- Cadastral boundary surveys (require sub-centimetre)\n"
        "- Construction layout (require centimetre)\n"
        "- Machine control (require centimetre real-time)"
    )

st.divider()

# ── Common questions ─────────────────────────────────────────────────────────
st.header("Common questions")

with st.expander("Why is my vertical accuracy so much worse than horizontal?"):
    st.markdown("""
    This is a fundamental limitation of GPS geometry, not a software issue.

    GPS satellites are always above the horizon — you never have a satellite directly
    below you. This means the geometry in the vertical direction is always weaker than
    in the horizontal plane. Mathematically, the VDOP (vertical dilution of precision)
    is always larger than HDOP.

    In practice, for standard SPP positioning:
    - Horizontal accuracy (RMSE_H): typically 50–100 m
    - Vertical accuracy (RMSE_V): typically 80–200 m

    This ratio of roughly 1.5–2x is normal and expected. RTK and PPP techniques
    reduce this gap but vertical accuracy is always slightly worse than horizontal.
    """)

with st.expander("Why does my accuracy change throughout the session?"):
    st.markdown("""
    GPS satellites move across the sky continuously. As they rise and set, the geometry
    changes — sometimes improving, sometimes degrading.

    You can see this in the HDOP time series plot. When HDOP drops suddenly, a new
    satellite has risen above the elevation mask and improved the geometry. When HDOP
    rises, a satellite has set and the remaining satellites are less well-spread.

    The accuracy jumps in the error time series correspond directly to these geometry
    changes. This is normal GPS behaviour and is not caused by any error in the software.
    """)

with st.expander("Why does my accuracy differ between day and night sessions?"):
    st.markdown("""
    Two factors cause day/night accuracy differences:

    **1. Ionospheric delay:** The ionosphere is most active during daylight hours when
    solar radiation ionizes the upper atmosphere. This adds 5–30 metres of delay to
    GPS signals. At night the ionosphere is quieter and delays are smaller (3–5 metres).
    The Klobuchar correction applied by this software corrects approximately 50% of
    this delay.

    **2. Satellite constellation:** The specific satellites visible depend on the time
    of day. Some times have better geometry than others regardless of atmospheric conditions.
    """)

with st.expander("What should I do if I have multipath-flagged satellites?"):
    st.markdown("""
    If you see multipath-flagged satellites, consider:

    **For future sessions:**
    - Move the receiver away from nearby buildings, walls, vehicles, or water surfaces
    - Use a higher elevation mask (15–20 degrees) to exclude low-elevation signals
    - Use a choke-ring antenna which physically rejects reflected signals
    - Choose observation times when high-elevation satellites provide good coverage

    **For this session's results:**
    - This software automatically downweights multipath satellites to 5% in the position calculation
    - The impact on accuracy depends on how many satellites were contaminated
    - If most satellites were multipath-free, the contaminated ones have minimal effect
    - If many satellites were flagged, the session accuracy may be significantly degraded
    """)

with st.expander("What is the difference between ellipsoidal height and elevation?"):
    st.markdown("""
    **Ellipsoidal height (h):** Height above the WGS84 mathematical ellipsoid — the
    smooth, mathematically defined surface that GPS uses as its reference. This is what
    GPS measures directly.

    **Orthometric height / elevation (H):** Height above the geoid — the surface
    that corresponds to mean sea level. This is what traditional surveying uses and
    what appears on topographic maps.

    The difference between the two is called the **geoid undulation (N)**:
    h = H + N

    In New Brunswick, N is approximately 21 metres — meaning ellipsoidal heights
    are about 21 metres higher than elevations above sea level. Nationally, N ranges
    from about -30 m to +30 m across Canada.

    **Always use ellipsoidal height in this software.** NRCan published coordinates
    always give ellipsoidal height.
    """)

st.divider()

# ── Glossary ────────────────────────────────────────────────────────────────
st.header("Glossary")
st.caption("Quick definitions for GNSS terms used in this software.")

glossary = {
    "Broadcast ephemeris": "The satellite orbit and clock parameters transmitted by GPS satellites themselves. Less accurate than precise ephemeris but available in real time.",
    "CEP (Circular Error Probable)": "A statistical measure of horizontal positioning accuracy. CEP50 = radius containing 50% of position fixes.",
    "CMC (Code-Minus-Carrier)": "The difference between the pseudorange and carrier phase measurements scaled to metres. Used to detect pseudorange multipath.",
    "DOP (Dilution of Precision)": "A dimensionless number describing how satellite geometry amplifies positioning errors. Lower is better.",
    "ECEF (Earth-Centred Earth-Fixed)": "A 3D coordinate system with origin at Earth's centre, X-axis toward 0° longitude, Z-axis toward North Pole.",
    "Ellipsoid": "A mathematically smooth surface approximating the shape of the Earth. WGS84 is the ellipsoid used by GPS.",
    "Epoch": "One complete set of measurements from all visible satellites at a single instant in time.",
    "Geoid": "The equipotential surface of Earth's gravity field that corresponds to mean sea level.",
    "GNSS (Global Navigation Satellite System)": "Any satellite navigation system. GPS (USA), GLONASS (Russia), Galileo (EU), BeiDou (China) are the four main systems.",
    "GPS (Global Positioning System)": "The US satellite navigation system operated by the US Space Force. Consists of 31 operational satellites.",
    "HDOP (Horizontal Dilution of Precision)": "DOP value for the horizontal plane only.",
    "IGS (International GNSS Service)": "A global network of GNSS tracking stations that provides free reference data and precise satellite orbit products.",
    "Ionosphere": "The layer of Earth's atmosphere from 60–1000 km altitude containing free electrons that slow GPS signals. Causes positioning errors of 5–30 metres.",
    "Klobuchar model": "An 8-coefficient mathematical model broadcast by GPS satellites to correct approximately 50% of ionospheric delay.",
    "Least squares": "A mathematical method for finding the best-fit solution to an overdetermined system of equations. Used to compute position from multiple satellite measurements.",
    "Multipath": "GPS signal error caused by the receiver picking up reflections of the satellite signal off surfaces. Corrupts the pseudorange measurement.",
    "NRCan (Natural Resources Canada)": "The Canadian government department responsible for the CORS network of continuously operating GPS reference stations.",
    "PDOP (Position Dilution of Precision)": "DOP value for all three dimensions (horizontal + vertical).",
    "PPP (Precise Point Positioning)": "A GPS technique achieving centimetre accuracy using precise satellite orbit and clock products.",
    "Pseudorange": "The measured distance from receiver to satellite, computed from signal travel time. Called pseudo because it contains clock and atmospheric errors.",
    "RINEX (Receiver Independent Exchange Format)": "A standardized text file format for GNSS data exchange. All major receiver manufacturers can export RINEX.",
    "RMSE (Root Mean Square Error)": "A statistical measure of error magnitude. √(mean of squared errors). Penalizes large outliers more than the mean.",
    "RTK (Real-Time Kinematic)": "A GPS technique achieving centimetre accuracy in real time using a nearby reference station.",
    "SNR (Signal-to-Noise Ratio)": "The ratio of GPS signal power to noise power, in dB-Hz. Higher is better. Typical range: 25–55 dB-Hz.",
    "SPP (Single Point Positioning)": "The fundamental GPS positioning technique using one receiver and broadcast satellite data. Accuracy: 1–100 m.",
    "Troposphere": "The lowest layer of Earth's atmosphere (0–10 km). Delays GPS signals by 2–30 metres depending on elevation angle and weather.",
    "WGS84 (World Geodetic System 1984)": "The global coordinate reference system used by GPS. Defines the ellipsoid, coordinate origin, and orientation.",
}

cols = st.columns(2)
items = sorted(glossary.items())
half  = len(items) // 2

with cols[0]:
    for term, definition in items[:half]:
        st.markdown(f"**{term}**")
        st.caption(definition)
        st.markdown("")

with cols[1]:
    for term, definition in items[half:]:
        st.markdown(f"**{term}**")
        st.caption(definition)
        st.markdown("")

st.divider()
st.markdown(
    '<div style="text-align:center;color:#666;font-size:12px">'
    'GNSS Positioning Quality Analyzer · '
    'Dweep Saha · Department of Geodesy & Geomatics Engineering · '
    'University of New Brunswick'
    '</div>',
    unsafe_allow_html=True
)