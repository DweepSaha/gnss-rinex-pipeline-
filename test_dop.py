import numpy as np
from src.gnss_pipeline.dop import compute_dop

# Test 1: realistic satellite geometry with varied azimuths and elevations
sat_data = [
    (45,  30),
    (120, 55),
    (200, 40),
    (290, 25),
    (15,  70),
    (160, 20),
]

H_rows = []
for az_deg, el_deg in sat_data:
    az = np.radians(az_deg)
    el = np.radians(el_deg)
    lx = -np.cos(el) * np.sin(az)
    ly = -np.cos(el) * np.cos(az)
    lz = -np.sin(el)
    H_rows.append([lx, ly, lz, 1.0])

H = np.array(H_rows)
dop = compute_dop(H)

print("DOP test with realistic satellite geometry:")
print(f"  GDOP: {dop['GDOP']}")
print(f"  PDOP: {dop['PDOP']}")
print(f"  HDOP: {dop['HDOP']}")
print(f"  VDOP: {dop['VDOP']}")
print()
print("Expected: HDOP < 1.5, PDOP < 2.5")

if dop["HDOP"] < 1.5 and dop["PDOP"] < 2.5:
    print("PASS — DOP values look correct")
else:
    print("FAIL — DOP values out of expected range")

# Test 2: fewer than 4 satellites — should return nan
H_small = np.array(H_rows[:3])
dop_small = compute_dop(H_small)
print()
print("DOP test with only 3 satellites (should return nan):")
print(f"  HDOP: {dop_small['HDOP']}")
if np.isnan(dop_small["HDOP"]):
    print("PASS — correctly returns nan for underdetermined geometry")
else:
    print("FAIL — should have returned nan")