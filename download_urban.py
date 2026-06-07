"""
Download urban canyon RINEX data for multipath testing.
Uses BKG IGS mirror — no registration required.
Station: WARN (Warnemunde, Germany — coastal urban)
        BRST (Brest, France — urban coastal)
        ALGO already have — rural baseline for comparison
Run from project root.
"""
import urllib.request
import gzip
import os
from pathlib import Path

Path("data/raw/extracted").mkdir(parents=True, exist_ok=True)

# We will try multiple urban stations and sources
# Day 152 of 2025 = June 1 2025 — same day as all your other data
# This keeps the comparison fair — same date, same satellites, different environment

downloads = [
    {
        "station":  "BRST",
        "desc":     "Brest, France — urban coastal city",
        "obs_url":  "https://igs.bkg.bund.de/root_ftp/IGS/obs/2025/152/brst1520.25o.gz",
        "nav_url":  "https://igs.bkg.bund.de/root_ftp/IGS/BRDC/2025/152/brdc1520.25n.gz",
        "obs_out":  "data/raw/extracted/BRST_20251520000_obs.rnx",
        "nav_out":  "data/raw/extracted/BRST_20251520000_nav.rnx",
    },
    {
        "station":  "WARN",
        "desc":     "Warnemunde, Germany — urban port city",
        "obs_url":  "https://igs.bkg.bund.de/root_ftp/IGS/obs/2025/152/warn1520.25o.gz",
        "nav_url":  "https://igs.bkg.bund.de/root_ftp/IGS/BRDC/2025/152/brdc1520.25n.gz",
        "obs_out":  "data/raw/extracted/WARN_20251520000_obs.rnx",
        "nav_out":  "data/raw/extracted/WARN_20251520000_nav.rnx",
    },
]


def download_and_extract(url: str, out_path: str) -> bool:
    """Download a gzipped file and extract it. Returns True if successful."""
    tmp_gz = out_path + ".gz"
    try:
        print(f"  Downloading {url.split('/')[-1]}...")
        urllib.request.urlretrieve(url, tmp_gz)

        # Check it is actually gzipped
        with open(tmp_gz, "rb") as f:
            magic = f.read(2)
        if magic != b"\x1f\x8b":
            print(f"  Not a gzip file — server may have returned an error page")
            os.remove(tmp_gz)
            return False

        # Decompress
        with gzip.open(tmp_gz, "rb") as f_in:
            with open(out_path, "wb") as f_out:
                f_out.write(f_in.read())
        os.remove(tmp_gz)
        size_mb = Path(out_path).stat().st_size / 1e6
        print(f"  Saved: {out_path} ({size_mb:.1f} MB)")
        return True

    except Exception as e:
        print(f"  Failed: {e}")
        if Path(tmp_gz).exists():
            os.remove(tmp_gz)
        return False


print("Downloading urban IGS station data for multipath testing")
print("=" * 60)

for dl in downloads:
    print(f"\nStation: {dl['station']} — {dl['desc']}")

    obs_ok = download_and_extract(dl["obs_url"], dl["obs_out"])
    nav_ok = download_and_extract(dl["nav_url"], dl["nav_out"])

    if obs_ok and nav_ok:
        print(f"  SUCCESS — {dl['station']} ready for testing")
    elif obs_ok:
        print(f"  PARTIAL — observation file downloaded, nav file failed")
        print(f"  Use your existing FRDN nav file as fallback")
    else:
        print(f"  FAILED — try manual download (see instructions below)")

print()
print("=" * 60)
print("If downloads failed, manual alternative:")
print("  Go to: https://igs.bkg.bund.de/root_ftp/IGS/obs/2025/152/")
print("  Download any station file ending in .25o.gz")
print("  Extract it and save to data/raw/extracted/")
print()
print("IGS station reference coordinates:")
print("  BRST: lat=48.380819  lon=-4.497269  h=65.469")
print("  WARN: lat=54.173500  lon=12.097800  h=66.000")