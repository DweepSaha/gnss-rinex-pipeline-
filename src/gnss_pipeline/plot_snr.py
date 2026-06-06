"""
SNR Visualization — Phase 3 Milestone 1

Generates:
  1. SNR time series per satellite
  2. SNR heatmap across all satellites and epochs
  3. Annotated sky plot colored by quality flag
"""
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from pathlib import Path

from src.gnss_pipeline.snr_analysis import QUALITY_CLEAN, QUALITY_SUSPECT, QUALITY_MULTIPATH

# Colors for quality flags — consistent across all Phase 3 plots
FLAG_COLORS = {
    QUALITY_CLEAN:     "#1D9E75",   # green
    QUALITY_SUSPECT:   "#BA7517",   # amber
    QUALITY_MULTIPATH: "#D85A30",   # red
}

FLAG_LABELS = {
    QUALITY_CLEAN:     "Clean",
    QUALITY_SUSPECT:   "Suspect",
    QUALITY_MULTIPATH: "Multipath",
}


def plot_snr_timeseries(session_snr: dict, output_path: str):
    """
    Plot SNR time series for all satellites in one figure.
    Each satellite gets its own panel, colored by quality flag.
    """
    sats = sorted(session_snr.keys())
    n    = len(sats)

    if n == 0:
        print("No satellites to plot.")
        return

    fig, axes = plt.subplots(
        n, 1,
        figsize=(14, max(2 * n, 8)),
        sharex=True
    )

    # Handle single satellite case
    if n == 1:
        axes = [axes]

    fig.suptitle("SNR Time Series — FRDN\n(GPS satellites)", fontsize=13)

    for i, sat in enumerate(sats):
        data   = session_snr[sat]
        snr    = data["snr"]
        flag   = data["result"]["flag"]
        color  = FLAG_COLORS[flag]
        mean_s = data["result"]["mean_snr"]
        mean_d = data["result"]["mean_deviation"]

        ax = axes[i]
        ax.plot(snr, color=color, linewidth=0.9)
        ax.axhline(35, color="gray", linewidth=0.5,
                   linestyle="--", alpha=0.5)
        ax.set_ylabel(sat, fontsize=9, rotation=0,
                      labelpad=28, va="center")
        ax.set_ylim(10, 60)
        ax.grid(True, alpha=0.2)

        # Quality label in top-right corner of each panel
        ax.text(
            0.99, 0.85,
            f"{FLAG_LABELS[flag]}  μ={mean_s:.0f} dB  σ={mean_d:.2f}",
            transform=ax.transAxes,
            fontsize=8,
            ha="right",
            color=color,
        )

    axes[-1].set_xlabel("Epoch index", fontsize=10)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {output_path}")


def plot_snr_heatmap(session_snr: dict, output_path: str):
    """
    SNR heatmap — rows are satellites, columns are epochs.
    Color intensity shows SNR strength.
    Satellite labels on Y axis are colored by quality flag.
    """
    sats = sorted(session_snr.keys())
    if not sats:
        return

    # Find maximum epoch count
    max_epochs = max(len(d["snr"]) for d in session_snr.values())

    # Build matrix — NaN where satellite has no data
    matrix = np.full((len(sats), max_epochs), np.nan)
    for i, sat in enumerate(sats):
        snr = session_snr[sat]["snr"]
        matrix[i, :len(snr)] = snr

    fig, ax = plt.subplots(figsize=(14, 6))

    im = ax.imshow(
        matrix,
        aspect="auto",
        interpolation="nearest",
        cmap="RdYlGn",
        vmin=20, vmax=55,
    )

    plt.colorbar(im, ax=ax, label="SNR (dB-Hz)", shrink=0.8)

    ax.set_yticks(range(len(sats)))
    ax.set_yticklabels(sats, fontsize=9)

    # Color satellite labels by quality flag
    for i, sat in enumerate(sats):
        flag  = session_snr[sat]["result"]["flag"]
        color = FLAG_COLORS[flag]
        ax.get_yticklabels()[i].set_color(color)

    ax.set_xlabel("Epoch index", fontsize=10)
    ax.set_title("SNR Heatmap — FRDN\n(green = strong signal, red = weak signal)", fontsize=12)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {output_path}")


def plot_quality_summary(session_snr: dict, output_path: str):
    """
    Bar chart showing mean SNR per satellite, colored by quality flag.
    """
    sats   = sorted(session_snr.keys())
    means  = [session_snr[s]["result"]["mean_snr"] for s in sats]
    devs   = [session_snr[s]["result"]["mean_deviation"] for s in sats]
    flags  = [session_snr[s]["result"]["flag"] for s in sats]
    colors = [FLAG_COLORS[f] for f in flags]

    fig, axes = plt.subplots(2, 1, figsize=(12, 7))
    fig.suptitle("SNR Quality Summary — FRDN", fontsize=13)

    # Panel 1: mean SNR
    bars = axes[0].bar(sats, means, color=colors, edgecolor="white", linewidth=0.5)
    axes[0].axhline(35, color="gray", linestyle="--",
                    linewidth=0.8, label="35 dB-Hz threshold")
    axes[0].set_ylabel("Mean SNR (dB-Hz)", fontsize=10)
    axes[0].set_title("Mean SNR per satellite", fontsize=10)
    axes[0].legend(fontsize=9)
    axes[0].grid(True, alpha=0.3, axis="y")
    axes[0].set_ylim(0, 60)

    # Panel 2: mean deviation
    axes[1].bar(sats, devs, color=colors, edgecolor="white", linewidth=0.5)
    axes[1].axhline(3.0, color="#BA7517", linestyle="--",
                    linewidth=0.8, label="Suspect threshold (3 dB-Hz)")
    axes[1].axhline(6.0, color="#D85A30", linestyle="--",
                    linewidth=0.8, label="Multipath threshold (6 dB-Hz)")
    axes[1].set_ylabel("Mean SNR deviation (dB-Hz)", fontsize=10)
    axes[1].set_title("SNR deviation per satellite (higher = more multipath)", fontsize=10)
    axes[1].legend(fontsize=9)
    axes[1].grid(True, alpha=0.3, axis="y")

    # Add flag labels on bars
    for i, (sat, flag) in enumerate(zip(sats, flags)):
        axes[1].text(
            i, devs[i] + 0.1,
            FLAG_LABELS[flag][0],  # first letter: C/S/M
            ha="center", fontsize=8,
            color=FLAG_COLORS[flag],
        )

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {output_path}")