# Add this to test_storm_iono.py temporarily after the imports
import numpy as np
from src.gnss_pipeline.corrections import klobuchar_iono_correction
from src.gnss_pipeline.nav_header_utils import get_nav_header

lat_r = np.radians(45.9335)
lon_r = np.radians(-66.6596)

quiet_hdr = get_nav_header(storm=False)
storm_hdr = get_nav_header(storm=True)

print("Klobuchar correction comparison — quiet vs storm coefficients")
print(f"{'UTC hour':<10} {'Quiet (m)':>12} {'Storm (m)':>12} {'Difference':>12}")
print("-" * 48)
for utc_hour in [0, 2, 6, 10, 14, 18, 20, 22]:
    tow = utc_hour * 3600 + 604800  # approximate GPS ToW
    q = klobuchar_iono_correction(quiet_hdr, np.radians(45), np.radians(180), lat_r, lon_r, tow)
    s = klobuchar_iono_correction(storm_hdr, np.radians(45), np.radians(180), lat_r, lon_r, tow)
    print(f"  {utc_hour:02d}:00       {q:>10.3f} m  {s:>10.3f} m  {s-q:>10.3f} m")