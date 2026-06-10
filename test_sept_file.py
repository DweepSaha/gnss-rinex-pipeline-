"""
Test loading the Septentrio RINEX file after cleaning.

Run from project root:
    python test_sept_file.py
"""

from pathlib import Path

import georinex as gr

from src.gnss_pipeline.rinex_cleaner import (
    clean_rinex_obs_file,
    summarize_rinex_text_file,
)


RAW_OBS = Path("data/raw/extracted/ObsGNSS_Aug25.rnx")
CLEAN_OBS = Path("data/raw/extracted/ObsGNSS_Aug25_cleaned_gps_1hz.rnx")


def main() -> None:
    print("=" * 80)
    print("Septentrio RINEX cleaning test")
    print("=" * 80)

    if not RAW_OBS.exists():
        raise FileNotFoundError(
            f"Could not find {RAW_OBS}. "
            "Make sure ObsGNSS_Aug25.rnx is inside data/raw/extracted."
        )

    print("\nStep 1 — Raw file text summary...")
    raw_summary = summarize_rinex_text_file(RAW_OBS)
    for key, value in raw_summary.items():
        print(f"  {key}: {value}")

    print("\nStep 2 — Cleaning raw file...")
    clean_rinex_obs_file(
        input_path=RAW_OBS,
        output_path=CLEAN_OBS,
        gps_only=True,
        whole_seconds_only=True,
    )

    print(f"  Cleaned file saved to: {CLEAN_OBS}")

    print("\nStep 3 — Cleaned file text summary...")
    cleaned_summary = summarize_rinex_text_file(CLEAN_OBS)
    for key, value in cleaned_summary.items():
        print(f"  {key}: {value}")

    print("\nStep 4 — Loading cleaned file with georinex...")
    obs = gr.load(CLEAN_OBS, use="G")

    epoch_count = len(obs.time.values)
    obs_types = list(obs.data_vars)
    gps_sats = [str(sv) for sv in obs.sv.values if str(sv).startswith("G")]

    print(f"  Epochs loaded:     {epoch_count}")
    print(f"  Observation types: {obs_types}")
    print(f"  GPS satellites:    {gps_sats}")

    if epoch_count > 0:
        print(f"  First timestamp:   {obs.time.values[0]}")
        print(f"  Last timestamp:    {obs.time.values[-1]}")
        print("\nSUCCESS: georinex loaded the cleaned Septentrio file.")
    else:
        raise ValueError("ERROR: georinex still loaded 0 epochs.")

    print("\nDone.")


if __name__ == "__main__":
    main()