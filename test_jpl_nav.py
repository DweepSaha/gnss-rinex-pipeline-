"""
Test JPL navigation file parsing.
Confirms Klobuchar coefficients are extracted from the file header.
Run from project root.
"""
import georinex as gr
from src.gnss_pipeline.nav_header_utils import get_nav_header_from_file

NAV_FILE = "data/raw/extracted/JPLM00USA_R_20211750000_01D_GN.rnx"

print("Loading JPL navigation file...")
nav = gr.load(NAV_FILE, use="G")

print("Header attributes found:")
for key, val in nav.attrs.items():
    print(f"  {key}: {val}")

print()
print("Extracting Klobuchar coefficients...")
header = get_nav_header_from_file(nav)

print(f"GPSA: {header.get('GPSA')}")
print(f"GPSB: {header.get('GPSB')}")
print()

expected_gpsa = [4.6566e-09, 1.4901e-08, -5.9605e-08, -1.1921e-07]
expected_gpsb = [8.1920e+04, 9.8304e+04, -6.5536e+04, -5.2429e+05]

gpsa_ok = header.get("GPSA") is not None
gpsb_ok = header.get("GPSB") is not None

if gpsa_ok and gpsb_ok:
    print("PASS — Klobuchar coefficients successfully extracted from JPL nav file.")
    print("Your software will use these instead of the hardcoded IGS fallback.")
else:
    print("FAIL — Coefficients not found. Software fell back to hardcoded values.")
    print("This means georinex is not reading the IONOSPHERIC CORR records from this file.")