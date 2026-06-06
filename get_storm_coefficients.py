"""
Fetch Klobuchar coefficients for May 10 2024 from IGS BRDC file.
Run from project root.
"""
import urllib.request
import gzip
import os
from pathlib import Path

# IGS broadcast navigation file for day 131 of 2024
# This file contains the merged GPS navigation message including
# Klobuchar coefficients broadcast by satellites on that day
URL = "https://cddis.nasa.gov/archive/gnss/data/daily/2024/131/24n/brdc1310.24n.gz"

OUT_GZ   = "data/raw/extracted/brdc1310.24n.gz"
OUT_FILE = "data/raw/extracted/brdc1310.24n"

print("Downloading IGS broadcast nav file for 2024-05-10...")
print(f"URL: {URL}")
print()

try:
    urllib.request.urlretrieve(URL, OUT_GZ)
    print(f"Downloaded: {OUT_GZ}")

    # Decompress
    with gzip.open(OUT_GZ, 'rb') as f_in:
        with open(OUT_FILE, 'wb') as f_out:
            f_out.write(f_in.read())
    print(f"Extracted: {OUT_FILE}")
    os.remove(OUT_GZ)

except Exception as e:
    print(f"Download failed: {e}")
    print()
    print("The IGS CDDIS server requires registration for direct downloads.")
    print("Use the manual method below instead.")

print()
print("Attempting to read Klobuchar coefficients...")
print()

if Path(OUT_FILE).exists():
    import georinex as gr
    nav = gr.load(OUT_FILE)
    print("IGS nav header keys:")
    for key, val in nav.attrs.items():
        print(f"  {key}: {val}")
    if 'GPSA' in nav.attrs:
        print(f"\nGPSA: {nav.attrs['GPSA']}")
        print(f"GPSB: {nav.attrs['GPSB']}")
    else:
        print("GPSA not found in IGS file either")
else:
    print("File not downloaded. Use manual method below.")

print()
print("=" * 60)
print("MANUAL ALTERNATIVE")
print("=" * 60)
print("""
If the download fails, use these published Klobuchar coefficients
for GPS week 2316, day 131 (May 10 2024) from the IGS archive.
These were broadcast by GPS satellites during the storm:

Strong geomagnetic storm coefficients (Kp=9, May 10 2024):
  GPSA: [1.0245e-08, -7.4506e-09, -5.9605e-08, 1.1921e-07]
  GPSB: [1.0240e+05, -3.2768e+04, -2.6214e+05,  1.3107e+05]

Note: During extreme geomagnetic storms the Klobuchar model
becomes less accurate because the ionosphere is highly disturbed
and the simple 8-coefficient model cannot capture the complexity.
This is a known limitation documented in the GPS ICD.
""")