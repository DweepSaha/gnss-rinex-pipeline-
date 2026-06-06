"""
Phase 3 Milestone 2 test — CMC multipath detection.
Run from project root.
"""
import georinex as gr
import numpy as np
from pathlib import Path
from src.gnss_pipeline.snr_analysis import analyse_session_snr
from src.gnss_pipeline.cmc_analysis import (
    analyse_session_cmc,
    combine_snr_cmc_flags,
    QUALITY_CLEAN, QUALITY_SUSPECT, QUALITY_MULTIPATH,
)
from src.gnss_pipeline.plot_cmc import (
    plot_cmc_timeseries,
    plot_cmc_summary,
    plot_combined_quality,
)

Path("outputs/plots").mkdir(parents=True, exist_ok=True)

OBS_FILE = "data/raw/extracted/FRDN00CAN_R_20251520000_01D_30S_MO.rnx"

print("Loading RINEX observation file...")
obs = gr.load(
    OBS_FILE,
    use="G",
    tlim=["2025-06-01T00:00:30", "2025-06-01T02:00:00"]
)
print(f"Epochs loaded: {len(obs.time.values)}")
print()

# Run both analyses
print("Running SNR analysis...")
snr_results = analyse_session_snr(obs, snr_field="S1C")

print("Running CMC analysis...")
cmc_results = analyse_session_cmc(obs)

print()
print("=" * 55)
print("CMC Multipath Report — FRDN")
print("=" * 55)

counts = {QUALITY_CLEAN: 0, QUALITY_SUSPECT: 0, QUALITY_MULTIPATH: 0}

for sat in sorted(cmc_results.keys()):
    r    = cmc_results[sat]["result"]
    flag = r["flag"]
    counts[flag] += 1
    slips = int(np.sum(cmc_results[sat]["slip_mask"]))
    print(
        f"  {sat}:  {flag:<10}  "
        f"std={r['std']:.4f} m  "
        f"rms={r['rms']:.4f} m  "
        f"max={r['max_abs']:.3f} m  "
        f"slips={slips}"
    )

print()
print(f"  Clean:     {counts[QUALITY_CLEAN]} satellites")
print(f"  Suspect:   {counts[QUALITY_SUSPECT]} satellites")
print(f"  Multipath: {counts[QUALITY_MULTIPATH]} satellites")
print("=" * 55)

# Combine SNR and CMC flags
print()
print("Combined quality flags (SNR + CMC):")
combined = combine_snr_cmc_flags(snr_results, cmc_results)
combined_counts = {QUALITY_CLEAN: 0, QUALITY_SUSPECT: 0, QUALITY_MULTIPATH: 0}
for sat in sorted(combined.keys()):
    flag = combined[sat]
    combined_counts[flag] += 1
    snr_flag = snr_results.get(sat, {}).get("result", {}).get("flag", "?")
    cmc_flag = cmc_results.get(sat, {}).get("result", {}).get("flag", "?")
    print(f"  {sat}:  SNR={snr_flag:<10} CMC={cmc_flag:<10} → {flag}")

print()
print(f"  Final clean:     {combined_counts[QUALITY_CLEAN]}")
print(f"  Final suspect:   {combined_counts[QUALITY_SUSPECT]}")
print(f"  Final multipath: {combined_counts[QUALITY_MULTIPATH]}")

# Generate plots
print()
print("Generating plots...")

plot_cmc_timeseries(
    cmc_results,
    "outputs/plots/cmc_timeseries_FRDN.png"
)

plot_cmc_summary(
    cmc_results,
    "outputs/plots/cmc_summary_FRDN.png"
)

plot_combined_quality(
    snr_results, cmc_results, combined,
    "outputs/plots/combined_quality_FRDN.png"
)

print()
print("Milestone 2 complete.")
print("Open outputs/plots/ to view the three new plots.")