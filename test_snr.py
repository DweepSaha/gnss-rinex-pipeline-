"""
Phase 3 Milestone 1 test — SNR analysis.
Run from project root.
"""
import georinex as gr
import numpy as np
from pathlib import Path
from src.gnss_pipeline.snr_analysis import (
    analyse_session_snr,
    QUALITY_CLEAN, QUALITY_SUSPECT, QUALITY_MULTIPATH
)
from src.gnss_pipeline.plot_snr import (
    plot_snr_timeseries,
    plot_snr_heatmap,
    plot_quality_summary,
)

Path("outputs/plots").mkdir(parents=True, exist_ok=True)

# Load 2 hours of FRDN data
OBS_FILE = "data/raw/extracted/FRDN00CAN_R_20251520000_01D_30S_MO.rnx"

print("Loading RINEX observation file...")
obs = gr.load(
    OBS_FILE,
    use="G",
    tlim=["2025-06-01T00:00:30", "2025-06-01T02:00:00"]
)

print(f"Observation types available: {list(obs.data_vars)}")
print(f"Epochs loaded: {len(obs.time.values)}")
print()

# Run SNR analysis
print("Running SNR analysis...")
session_snr = analyse_session_snr(obs, snr_field="S1C")

print(f"Satellites analysed: {len(session_snr)}")
print()

# Print quality report
print("=" * 50)
print("SNR Quality Report — FRDN")
print("=" * 50)

counts = {QUALITY_CLEAN: 0, QUALITY_SUSPECT: 0, QUALITY_MULTIPATH: 0}

for sat in sorted(session_snr.keys()):
    r    = session_snr[sat]["result"]
    flag = r["flag"]
    counts[flag] += 1
    flag_display = f"{flag:<10}"
    print(
        f"  {sat}:  {flag_display}  "
        f"mean SNR={r['mean_snr']:.1f} dB  "
        f"deviation={r['mean_deviation']:.3f} dB  "
        f"low%={r['pct_low']:.1f}%"
    )

print()
print(f"  Clean:     {counts[QUALITY_CLEAN]} satellites")
print(f"  Suspect:   {counts[QUALITY_SUSPECT]} satellites")
print(f"  Multipath: {counts[QUALITY_MULTIPATH]} satellites")
print("=" * 50)

# Generate plots
print()
print("Generating plots...")

plot_snr_timeseries(
    session_snr,
    "outputs/plots/snr_timeseries_FRDN.png"
)

plot_snr_heatmap(
    session_snr,
    "outputs/plots/snr_heatmap_FRDN.png"
)

plot_quality_summary(
    session_snr,
    "outputs/plots/snr_quality_summary_FRDN.png"
)

print()
print("Milestone 1 complete.")
print("Open outputs/plots/ in VS Code to view the three plots.")