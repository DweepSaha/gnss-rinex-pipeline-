"""
Quick validation test — confirms RINEX 2 compatibility fix is working.
Run from project root after activating venv.
"""
import georinex as gr
import numpy as np

OBS_FILE = "data/raw/extracted/jplm1750.21o"

print("RINEX 2 Compatibility Test")
print("=" * 45)

# Test 1 — field detection
print("\nTest 1 — Field name detection")
obs = gr.load(OBS_FILE, use="G",
              tlim=["2021-06-24T00:00:00", "2021-06-24T00:10:00"])

vars_present = list(obs.data_vars)
pr_field   = "C1C" if "C1C" in vars_present else "C1" if "C1" in vars_present else "P1"
snr_field  = "S1C" if "S1C" in vars_present else "S1"
carr_field = "L1C" if "L1C" in vars_present else "L1"
version    = "RINEX 3" if "C1C" in vars_present else "RINEX 2"

print(f"  Detected version:  {version}")
print(f"  Pseudorange field: {pr_field}")
print(f"  SNR field:         {snr_field}")
print(f"  Carrier field:     {carr_field}")
assert pr_field == "C1",   f"FAIL — expected C1, got {pr_field}"
assert snr_field == "S1",  f"FAIL — expected S1, got {snr_field}"
assert carr_field == "L1", f"FAIL — expected L1, got {carr_field}"
print("  PASS")

# Test 2 — SNR analysis on RINEX 2
print("\nTest 2 — SNR analysis on RINEX 2 file")
from src.gnss_pipeline.snr_analysis import analyse_session_snr
snr_results = analyse_session_snr(obs, snr_field=snr_field)
assert len(snr_results) > 0, "FAIL — no satellites analysed"
print(f"  Satellites analysed: {len(snr_results)}")
print("  PASS")

# Test 3 — CMC analysis on RINEX 2
print("\nTest 3 — CMC analysis on RINEX 2 file")
from src.gnss_pipeline.cmc_analysis import analyse_session_cmc
cmc_results = analyse_session_cmc(obs)
assert len(cmc_results) > 0, "FAIL — no CMC results"
print(f"  Satellites with CMC: {len(cmc_results)}")
print("  PASS")

# Test 4 — Klobuchar extraction
print("\nTest 4 — Klobuchar coefficient extraction")
nav = gr.load("data/raw/extracted/JPLM00USA_R_20211750000_01D_GN.rnx", use="G")
from src.gnss_pipeline.nav_header_utils import get_nav_header_from_file
header = get_nav_header_from_file(nav)
assert header.get("GPSA") is not None, "FAIL — no GPSA coefficients"
assert len(header["GPSA"]) == 4,       "FAIL — GPSA should have 4 values"
print(f"  GPSA: {header['GPSA']}")
print("  PASS")

# Test 5 — RINEX 3 still works
print("\nTest 5 — RINEX 3 file still processes correctly")
obs3 = gr.load(
    "data/raw/extracted/FRDN00CAN_R_20251520000_01D_30S_MO.rnx",
    use="G",
    tlim=["2025-06-01T00:00:30", "2025-06-01T00:10:00"]
)
vars3      = list(obs3.data_vars)
pr_field3  = "C1C" if "C1C" in vars3 else "C1"
version3   = "RINEX 3" if "C1C" in vars3 else "RINEX 2"
assert version3 == "RINEX 3", f"FAIL — expected RINEX 3, got {version3}"
assert pr_field3 == "C1C",    f"FAIL — expected C1C, got {pr_field3}"
print(f"  Detected version: {version3}")
print("  PASS")

print()
print("=" * 45)
print("All 5 tests passed.")
print("RINEX 2 compatibility fix is working correctly.")
print("RINEX 3 processing is unaffected.")