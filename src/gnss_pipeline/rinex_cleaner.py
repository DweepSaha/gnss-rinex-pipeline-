"""
RINEX cleaning utilities.

This module fixes receiver-specific RINEX formatting issues before loading
files with georinex.

Main problems solved:
1. Some Septentrio RINEX 3 files contain epoch lines such as:
       > 2021 06 24 12 00 1.00000000  0 27

   georinex 1.16.2 expects fixed-column epoch formatting, where seconds
   must be readable using fixed slices like ln[19:21].

   This cleaner rewrites epoch lines into strict RINEX 3 format:
       > 2021 06 24 12 00 01.0000000  0 11

2. Some receiver-exported files may contain duplicate GPS satellite IDs
   within the same epoch after filtering. For example:
       G 1
       G01

   georinex later normalizes these both to G01, causing xarray to crash
   because the sv coordinate has duplicate values.

   This cleaner normalizes satellite IDs to G## format and keeps only one
   observation line per GPS satellite per epoch.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple


def normalize_epoch_line(
    line: str,
    satellite_count: int | None = None,
) -> str:
    """
    Rewrite a RINEX 3 epoch line into strict fixed-width format.

    Example input:
        > 2021 06 24 12 00 1.00000000  0 27

    Example output:
        > 2021 06 24 12 00 01.0000000  0 27
    """
    parts = line.split()

    if len(parts) < 9 or parts[0] != ">":
        raise ValueError(f"Not a valid RINEX 3 epoch line: {line!r}")

    year = int(parts[1])
    month = int(parts[2])
    day = int(parts[3])
    hour = int(parts[4])
    minute = int(parts[5])
    second = float(parts[6])
    flag = int(parts[7])

    if satellite_count is None:
        satellite_count = int(parts[8])

    # Strict RINEX 3 epoch formatting.
    #
    # georinex 1.16.2 reads:
    #   year        = ln[2:6]
    #   month       = ln[7:9]
    #   day         = ln[10:12]
    #   hour        = ln[13:15]
    #   minute      = ln[16:18]
    #   second      = ln[19:21]
    #   microsecond = ln[19:29]
    #
    # Therefore seconds must be fixed-width:
    #   1.00000000  ->  01.0000000
    #
    # The satellite count is written as a 3-character field after the flag.
    return (
        f"> {year:04d} {month:02d} {day:02d} "
        f"{hour:02d} {minute:02d} {second:010.7f}  "
        f"{flag:1d}{satellite_count:3d}\n"
    )


def _parse_epoch_header(line: str) -> Tuple[int, int, float]:
    """
    Return epoch flag, satellite count, and seconds value from an epoch line.

    Uses split() because the source file may not be fixed-width yet.
    """
    parts = line.split()

    if len(parts) < 9 or parts[0] != ">":
        raise ValueError(f"Invalid epoch header: {line!r}")

    second = float(parts[6])
    flag = int(parts[7])
    nsat = int(parts[8])

    return flag, nsat, second


def _normalize_and_deduplicate_gps_obs_lines(obs_lines: List[str]) -> List[str]:
    """
    Keep GPS observation lines, normalize satellite IDs, and remove duplicates.

    Why this is needed:
    Some receiver-exported RINEX files may contain satellite IDs like:
        G 1
    while others use:
        G01

    georinex later normalizes spaces to zeros, so both become G01.
    If both exist in the same epoch, xarray crashes because the sv coordinate
    has duplicate values.

    This function guarantees one line per GPS satellite per epoch.
    """
    unique: dict[str, str] = {}

    for line in obs_lines:
        if not line.startswith("G"):
            continue

        # First 3 characters should contain the satellite ID.
        # Examples:
        #   "G01"
        #   "G 1"
        raw_sv = line[:3]

        try:
            prn = int(raw_sv[1:].strip())
        except ValueError:
            # Malformed satellite ID; skip it.
            continue

        sv = f"G{prn:02d}"

        # Rewrite the first 3 characters so georinex sees a clean satellite ID.
        normalized_line = sv + line[3:]

        # Keep only the first observation line for each satellite in this epoch.
        if sv not in unique:
            unique[sv] = normalized_line

    # Sort for stable, predictable output: G01, G02, G03, ...
    return [unique[sv] for sv in sorted(unique.keys())]


def _clean_header_line(line: str, gps_only: bool) -> str | None:
    """
    Clean one RINEX header line.

    Returns:
        - cleaned line
        - None if the line should be removed
    """
    # Remove malformed or problematic time records.
    # Your previous georinex failure involved TIME OF FIRST OBS.
    if "TIME OF FIRST OBS" in line or "TIME OF LAST OBS" in line:
        return None

    # If GPS-only, remove non-GPS observation type header lines.
    if gps_only and "SYS / # / OBS TYPES" in line:
        system = line[0:1]
        if system != "G":
            return None

    # If GPS-only, change file type from M mixed to G GPS.
    if gps_only and "RINEX VERSION / TYPE" in line:
        # RINEX file type is normally near column 41.
        # Example:
        #   3.04           OBSERVATION DATA    M
        if len(line) > 40 and line[40] == "M":
            line = line[:40] + "G" + line[41:]

    return line


def clean_rinex_obs_file(
    input_path: str | Path,
    output_path: str | Path,
    gps_only: bool = True,
    whole_seconds_only: bool = True,
) -> Path:
    """
    Clean a RINEX observation file for georinex compatibility.

    What this does:
    1. Normalizes line endings.
    2. Removes problematic TIME OF FIRST/LAST OBS header records.
    3. Optionally changes mixed file type M to GPS file type G.
    4. Optionally removes non-GPS observation type header lines.
    5. Rewrites epoch lines into fixed-width format.
    6. If gps_only=True, keeps only GPS satellite observation lines.
    7. Normalizes GPS satellite IDs to G## format.
    8. Removes duplicate GPS satellites within each epoch.
    9. Rewrites the epoch satellite count to match kept satellites.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input RINEX file not found: {input_path}")

    raw = input_path.read_bytes()

    text = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n").decode(
        "utf-8",
        errors="replace",
    )

    lines = text.splitlines(keepends=True)

    output: List[str] = []
    i = 0
    in_header = True

    total_epochs_seen = 0
    total_epochs_written = 0

    while i < len(lines):
        line = lines[i]

        if in_header:
            cleaned = _clean_header_line(line, gps_only=gps_only)

            if cleaned is not None:
                output.append(cleaned)

            if "END OF HEADER" in line:
                in_header = False

            i += 1
            continue

        # Epoch block begins.
        if line.startswith(">"):
            total_epochs_seen += 1

            try:
                _flag, nsat_original, sec_val = _parse_epoch_header(line)
            except Exception:
                # Skip malformed epoch header.
                i += 1
                continue

            obs_lines: List[str] = []
            j = i + 1

            # Read the satellite observation lines belonging to this epoch.
            for _ in range(nsat_original):
                if j >= len(lines):
                    break
                obs_lines.append(lines[j])
                j += 1

            # Optionally keep only whole-second epochs.
            #
            # Your raw file starts at 0.5, 0.6, etc.
            # With whole_seconds_only=True, this keeps:
            #   1.0, 2.0, 3.0, ...
            # and removes:
            #   0.5, 0.6, 0.7, ...
            if whole_seconds_only and abs(sec_val - round(sec_val)) > 1e-9:
                i = j
                continue

            # GPS-only path:
            # - keep only G satellites
            # - normalize G 1 -> G01
            # - remove duplicate satellite IDs inside the same epoch
            if gps_only:
                obs_lines = _normalize_and_deduplicate_gps_obs_lines(obs_lines)

            # Non-GPS-only path:
            # Keep the original observation lines. This is less robust for
            # your current Septentrio problem, so GPS-only is recommended.
            else:
                obs_lines = [obs for obs in obs_lines if obs.strip()]

            # If no usable satellite observations remain, skip this epoch.
            if not obs_lines:
                i = j
                continue

            normalized_epoch = normalize_epoch_line(
                line,
                satellite_count=len(obs_lines),
            )

            output.append(normalized_epoch)
            output.extend(obs_lines)

            total_epochs_written += 1
            i = j
            continue

        # Non-epoch body line outside an epoch block.
        i += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(output), encoding="utf-8", newline="\n")

    if total_epochs_seen == 0:
        raise ValueError(
            "Cleaner found 0 epoch headers. This does not look like a RINEX 3 "
            "observation file body."
        )

    if total_epochs_written == 0:
        raise ValueError(
            "Cleaner wrote 0 epochs. This means no usable GPS epochs were found "
            "after filtering. Check whether the file contains GPS observations."
        )

    return output_path


def summarize_rinex_text_file(path: str | Path) -> dict:
    """
    Return a simple text-level summary of a RINEX file.

    This does not use georinex; it only inspects the text.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"RINEX file not found: {path}")

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    epoch_lines = [line for line in lines if line.startswith(">")]
    gps_obs_lines = [line for line in lines if line.startswith("G")]
    glonass_obs_lines = [line for line in lines if line.startswith("R")]
    galileo_obs_lines = [line for line in lines if line.startswith("E")]
    beidou_obs_lines = [line for line in lines if line.startswith("C")]

    return {
        "path": str(path),
        "total_lines": len(lines),
        "epoch_lines": len(epoch_lines),
        "gps_observation_lines": len(gps_obs_lines),
        "glonass_observation_lines": len(glonass_obs_lines),
        "galileo_observation_lines": len(galileo_obs_lines),
        "beidou_observation_lines": len(beidou_obs_lines),
        "first_epoch": epoch_lines[0] if epoch_lines else None,
        "second_epoch": epoch_lines[1] if len(epoch_lines) > 1 else None,
    }