"""
Navigation header utilities — Phase 3 Milestone 4

Provides Klobuchar ionospheric correction coefficients.

NRCan RINEX 3 navigation files omit GPSA/GPSB header records.
We use IGS-published coefficients as fallback.

Quiet day:  GPS week 2369, June 1 2025  (Kp ~ 1)
Storm day:  GPS week 2316, May 10 2024  (Kp = 9, extreme storm)
"""

# --- Quiet day coefficients ---
# GPS week 2369, day 152 (2025-06-01)
GPSA_QUIET = [
     1.3039e-08,
     2.9802e-08,
    -1.1921e-07,
    -1.1921e-07,
]
GPSB_QUIET = [
     1.2288e+05,
     1.3107e+05,
    -1.3107e+05,
    -5.2429e+05,
]

# --- Storm day coefficients ---
# GPS week 2316, day 131 (2024-05-10) — Kp=9 extreme geomagnetic storm
GPSA_STORM = [
     1.0245e-08,
    -7.4506e-09,
    -5.9605e-08,
     1.1921e-07,
]
GPSB_STORM = [
     1.0240e+05,
    -3.2768e+04,
    -2.6214e+05,
     1.3107e+05,
]


def get_nav_header(storm: bool = False) -> dict:
    """
    Return nav header dict with appropriate Klobuchar coefficients.

    storm=False: quiet day coefficients (June 2025 session)
    storm=True:  storm day coefficients (May 2024 session)
    """
    if storm:
        return {"GPSA": GPSA_STORM, "GPSB": GPSB_STORM}
    return {"GPSA": GPSA_QUIET, "GPSB": GPSB_QUIET}


def get_nav_header_from_file(nav, storm: bool = False) -> dict:
    """
    Try to extract Klobuchar coefficients from a loaded georinex nav dataset.
    Tries multiple attribute key formats used by different georinex versions.
    Falls back to published IGS values if not found in the file.
    """
    gpsa = None
    gpsb = None

    # Try standard RINEX 3 keys first
    gpsa = nav.attrs.get("GPSA", None)
    gpsb = nav.attrs.get("GPSB", None)

    # Try RINEX 2 style keys if not found
    if gpsa is None:
        gpsa = nav.attrs.get("ION ALPHA", None)
    if gpsb is None:
        gpsb = nav.attrs.get("ION BETA", None)

    # Scan all attrs for any key containing GPSA or GPSB
    if gpsa is None or gpsb is None:
        for key, val in nav.attrs.items():
            key_upper = str(key).upper()
            if "GPSA" in key_upper and gpsa is None:
                gpsa = val
            if "GPSB" in key_upper and gpsb is None:
                gpsb = val

    if gpsa is not None and gpsb is not None:
        print("  Using Klobuchar coefficients from navigation file.")
        return {"GPSA": list(gpsa), "GPSB": list(gpsb)}

    # Fall back to hardcoded IGS values
    header = get_nav_header(storm=storm)
    label  = "storm day" if storm else "quiet day"
    print(f"  Nav file has no GPSA/GPSB — using IGS {label} coefficients.")
    return header