"""
Test ionospheric correction — Phase 3 Milestone 4
Verifies Klobuchar model produces physically realistic corrections.
Run from project root.
"""
import numpy as np
from src.gnss_pipeline.corrections import klobuchar_iono_correction
from src.gnss_pipeline.nav_header_utils import get_nav_header

nav_header = get_nav_header()
print("Klobuchar coefficients loaded:")
print(f"  GPSA: {nav_header['GPSA']}")
print(f"  GPSB: {nav_header['GPSB']}")
print()

# FRDN approximate position
lat_r = np.radians(45.9335)
lon_r = np.radians(-66.6596)

# GPS time of week for 2025-06-01 00:00:30
gps_time = 604830.0

print("Ionospheric delay estimates for FRDN satellites:")
print(f"{'Satellite':<12} {'Elevation':>10} {'Azimuth':>10} {'Iono delay':>12}")
print("-" * 48)

test_cases = [
    ("G10", 55.7, 180.0),
    ("G12", 28.1, 270.0),
    ("G23", 45.0,  90.0),
    ("G32", 60.0, 135.0),
    ("G18", 22.7,  45.0),
]

for sat, el_deg, az_deg in test_cases:
    el_rad = np.radians(el_deg)
    az_rad = np.radians(az_deg)

    iono_m = klobuchar_iono_correction(
        nav_header,
        el_rad,
        az_rad,
        lat_r,
        lon_r,
        gps_time,
    )

    print(f"  {sat:<10} {el_deg:>9.1f}°  {az_deg:>9.1f}°  {iono_m:>10.3f} m")

print()
print("Expected: delays between 2 and 15 metres.")
print("Higher elevation = less delay (shorter path through ionosphere).")
print("Night time (GPS ToW near 604800 ≈ midnight UTC) = smaller delays.")

all_ok = True
for sat, el_deg, az_deg in test_cases:
    iono_m = klobuchar_iono_correction(
        nav_header,
        np.radians(el_deg),
        np.radians(az_deg),
        lat_r, lon_r,
        gps_time,
    )
    if not (0.5 < iono_m < 25.0):
        print(f"FAIL: {sat} iono={iono_m:.3f} m out of expected range")
        all_ok = False

if all_ok:
    print()
    print("PASS — all ionospheric corrections within expected range.")