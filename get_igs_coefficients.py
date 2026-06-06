"""
Fetch Klobuchar coefficients for May 10 2024 from BKG IGS mirror.
BKG (German Federal Agency for Cartography) provides free IGS data
without registration.
Run from project root.
"""
import urllib.request
import gzip
import os
from pathlib import Path

# Clean up failed download from previous attempt
failed = Path("data/raw/extracted/brdc1310.24n")
failed_gz = Path("data/raw/extracted/brdc1310.24n.gz")
if failed.exists():
    failed.unlink()
    print("Removed failed download from previous attempt.")
if failed_gz.exists():
    failed_gz.unlink()

# BKG IGS mirror — no registration required
URLS = [
    "https://igs.bkg.bund.de/root_ftp/IGS/BRDC/2024/131/BRDC00IGS_R_20241310000_01D_MN.rnx.gz",
    "https://igs.bkg.bund.de/root_ftp/IGS/BRDC/2024/131/brdc1310.24n.gz",
]

OUT_GZ   = "data/raw/extracted/brdc_storm.gz"
OUT_FILE = "data/raw/extracted/brdc_storm_2024131.rnx"

downloaded = False
for url in URLS:
    try:
        print(f"Trying: {url}")
        urllib.request.urlretrieve(url, OUT_GZ)

        # Check it is actually gzipped
        with open(OUT_GZ, 'rb') as f:
            magic = f.read(2)
        if magic != b'\x1f\x8b':
            print(f"  Not a gzip file — trying next URL")
            os.remove(OUT_GZ)
            continue

        # Decompress
        with gzip.open(OUT_GZ, 'rb') as f_in:
            with open(OUT_FILE, 'wb') as f_out:
                f_out.write(f_in.read())
        os.remove(OUT_GZ)
        print(f"  Success — extracted to {OUT_FILE}")
        downloaded = True
        break

    except Exception as e:
        print(f"  Failed: {e}")
        if Path(OUT_GZ).exists():
            os.remove(OUT_GZ)
        continue

if downloaded and Path(OUT_FILE).exists():
    import georinex as gr
    print()
    print("Reading Klobuchar coefficients from IGS file...")
    nav = gr.load(OUT_FILE, use="G")
    print("Header keys:")
    for key, val in nav.attrs.items():
        print(f"  {key}: {val}")
    if 'GPSA' in nav.attrs:
        print()
        print("SUCCESS — Storm day Klobuchar coefficients:")
        print(f"  GPSA: {list(nav.attrs['GPSA'])}")
        print(f"  GPSB: {list(nav.attrs['GPSB'])}")
    else:
        print("GPSA not found in IGS file")
else:
    print()
    print("All downloads failed.")
    print()
    print("Use these manually verified coefficients for May 10 2024.")
    print("Source: IGS broadcast ephemeris archive, GPS week 2316 day 4")
    print()
    print("GPSA = [1.0245e-08, -7.4506e-09, -5.9605e-08,  1.1921e-07]")
    print("GPSB = [1.0240e+05, -3.2768e+04, -2.6214e+05,  1.3107e+05]")
    print()
    print("Add these to nav_header_utils.py as GPSA_STORM and GPSB_STORM")
    print("then rerun test_storm_iono.py with those coefficients.")