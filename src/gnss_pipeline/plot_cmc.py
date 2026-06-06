"""
CMC Visualization — Phase 3 Milestone 2

Generates:
  1. CMC time series per satellite with cycle slip markers
  2. CMC standard deviation bar chart colored by quality flag
  3. Combined SNR + CMC annotated sky plot
"""
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path

from src.gnss_pipeline.cmc_analysis import (
    QUALITY_CLEAN, QUALITY_SUSPECT, QUALITY_MULTIPATH
)

FLAG_COLORS = {
    QUALITY_CLEAN:     "#1D9E75",
    QUALITY_SUSPECT:   "#BA7517",
    QUALITY_MULTIPATH: "#D85A30",
}

FLAG_LABELS = {
    QUALITY_CLEAN:     "Clean",
    QUALITY_SUSPECT:   "Suspect",
    QUALITY_MULTIPATH: "Multipath",
}


def plot_cmc_timeseries(cmc_results: dict, output_path: str):
    """
    Plot detrended CMC time series for all satellites.
    Cycle slips marked with vertical red lines.
    """
    sats = sorted(cmc_results.keys())
    n    = len(sats)

    if n == 0:
        print("No satellites to plot.")
        return

    fig, axes = plt.subplots(n, 1, figsize=(14, max(2*n, 8)), sharex=True)
    if n == 1:
        axes = [axes]

    fig.suptitle(
        "Code-Minus-Carrier (CMC) Time Series — FRDN\n"
        "(detrended, ambiguity removed — variation = multipath)",
        fontsize=13
    )

    for i, sat in enumerate(sats):
        data          = cmc_results[sat]
        cmc           = data["cmc_detrended"]
        slip_mask     = data["slip_mask"]
        result        = data["result"]
        flag          = result["flag"]
        color         = FLAG_COLORS[flag]

        ax = axes[i]
        x  = np.arange(len(cmc))

        # Plot CMC
        ax.plot(x, cmc, color=color, linewidth=0.8, alpha=0.9)

        # Shade ±0.5 m band — the multipath detection threshold
        ax.axhspan(-0.5, 0.5, color="gray", alpha=0.08)
        ax.axhline(0, color="gray", linewidth=0.4, alpha=0.5)
        ax.axhline( 0.5, color="#D85A30", linewidth=0.4,
                   linestyle="--", alpha=0.4)
        ax.axhline(-0.5, color="#D85A30", linewidth=0.4,
                   linestyle="--", alpha=0.4)

        # Mark cycle slips
        slip_indices = np.where(slip_mask)[0]
        for idx in slip_indices:
            ax.axvline(idx, color="purple", linewidth=0.8,
                      linestyle=":", alpha=0.7)

        ax.set_ylabel(sat, fontsize=9, rotation=0,
                     labelpad=28, va="center")
        ax.set_ylim(-3, 3)
        ax.grid(True, alpha=0.2)

        # Stats label
        std_val = result["std"]
        label   = (
            f"{FLAG_LABELS[flag]}  "
            f"std={std_val:.3f} m  "
            f"slips={int(np.sum(slip_mask))}"
        )
        ax.text(0.99, 0.82, label,
               transform=ax.transAxes,
               fontsize=8, ha="right", color=color)

    axes[-1].set_xlabel("Epoch index", fontsize=10)

    # Legend
    patches = [
        mpatches.Patch(color="#1D9E75", label="Clean (std < 0.3 m)"),
        mpatches.Patch(color="#BA7517", label="Suspect (std 0.3–0.5 m)"),
        mpatches.Patch(color="#D85A30", label="Multipath (std > 0.5 m)"),
        mpatches.Patch(color="purple",  label="Cycle slip"),
    ]
    fig.legend(handles=patches, loc="upper right",
              fontsize=8, ncol=4, bbox_to_anchor=(0.99, 0.99))

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {output_path}")


def plot_cmc_summary(cmc_results: dict, output_path: str):
    """
    Bar chart of CMC standard deviation per satellite.
    Colored by quality flag with threshold lines.
    """
    sats   = sorted(cmc_results.keys())
    stds   = [cmc_results[s]["result"]["std"] for s in sats]
    flags  = [cmc_results[s]["result"]["flag"] for s in sats]
    colors = [FLAG_COLORS[f] for f in flags]

    fig, ax = plt.subplots(figsize=(12, 5))

    ax.bar(sats, stds, color=colors, edgecolor="white", linewidth=0.5)

    ax.axhline(0.3, color="#BA7517", linestyle="--", linewidth=1.2,
              label="Suspect threshold (0.3 m)")
    ax.axhline(0.5, color="#D85A30", linestyle="--", linewidth=1.2,
              label="Multipath threshold (0.5 m)")

    ax.set_ylabel("CMC standard deviation (m)", fontsize=11)
    ax.set_xlabel("Satellite", fontsize=11)
    ax.set_title(
        "CMC Multipath Indicator — FRDN\n"
        "(lower = cleaner signal)",
        fontsize=12
    )
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")

    # Add value labels on bars
    for i, (sat, std) in enumerate(zip(sats, stds)):
        if not np.isnan(std):
            ax.text(i, std + 0.005, f"{std:.3f}",
                   ha="center", fontsize=7,
                   color=FLAG_COLORS[flags[i]])

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {output_path}")


def plot_combined_quality(snr_results: dict, cmc_results: dict,
                          combined_flags: dict, output_path: str):
    """
    Side-by-side comparison of SNR flags vs CMC flags vs combined flag.
    Shows how the two methods agree or disagree per satellite.
    """
    all_sats = sorted(set(
        list(snr_results.keys()) + list(cmc_results.keys())
    ))

    flag_to_num = {QUALITY_CLEAN: 0, QUALITY_SUSPECT: 1, QUALITY_MULTIPATH: 2}
    num_to_label = {0: "Clean", 1: "Suspect", 2: "Multipath"}
    cmap_colors = ["#1D9E75", "#BA7517", "#D85A30"]

    snr_nums  = [flag_to_num.get(
        snr_results.get(s, {}).get("result", {}).get("flag", "suspect"), 1
    ) for s in all_sats]
    cmc_nums  = [flag_to_num.get(
        cmc_results.get(s, {}).get("result", {}).get("flag", "suspect"), 1
    ) for s in all_sats]
    comb_nums = [flag_to_num.get(
        combined_flags.get(s, "suspect"), 1
    ) for s in all_sats]

    fig, axes = plt.subplots(3, 1, figsize=(12, 7), sharex=True)
    fig.suptitle("Signal Quality Assessment — FRDN\nSNR vs CMC vs Combined", fontsize=13)

    for ax, nums, title in zip(
        axes,
        [snr_nums, cmc_nums, comb_nums],
        ["SNR flag", "CMC flag", "Combined flag"],
    ):
        bars = ax.bar(
            all_sats, [1]*len(all_sats),
            color=[cmap_colors[n] for n in nums],
            edgecolor="white", linewidth=0.5
        )
        for j, (sat, n) in enumerate(zip(all_sats, nums)):
            ax.text(j, 0.5, num_to_label[n],
                   ha="center", va="center",
                   fontsize=8, color="white", fontweight="bold")
        ax.set_ylabel(title, fontsize=10)
        ax.set_yticks([])
        ax.grid(False)

    axes[-1].set_xlabel("Satellite", fontsize=10)

    patches = [
        mpatches.Patch(color="#1D9E75", label="Clean"),
        mpatches.Patch(color="#BA7517", label="Suspect"),
        mpatches.Patch(color="#D85A30", label="Multipath"),
    ]
    fig.legend(handles=patches, loc="upper right", fontsize=9)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved: {output_path}")