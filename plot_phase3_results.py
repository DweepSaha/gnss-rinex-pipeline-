"""
Phase 3 final visualization — generates all portfolio plots.
Run from project root after process_session.py and
save_phase2_baseline.py have both been executed.
"""
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
from pathlib import Path

Path("outputs/plots").mkdir(parents=True, exist_ok=True)

# --- Load Phase 2 baseline results ---
p2_errors_h     = np.load("data/processed/p2_errors_h.npy")
p2_errors_v     = np.load("data/processed/p2_errors_v.npy")
p2_north_errors = np.load("data/processed/p2_north_errors.npy")
p2_east_errors  = np.load("data/processed/p2_east_errors.npy")

# --- Load Phase 3 results ---
p3_errors_h     = np.load("data/processed/errors_h.npy")
p3_errors_v     = np.load("data/processed/errors_v.npy")
p3_north_errors = np.load("data/processed/north_errors.npy")
p3_east_errors  = np.load("data/processed/east_errors.npy")

# --- Compute statistics ---
def stats(eh, ev):
    return {
        "cep50":  float(np.percentile(eh, 50)),
        "cep95":  float(np.percentile(eh, 95)),
        "rmse_h": float(np.sqrt(np.mean(eh**2))),
        "rmse_v": float(np.sqrt(np.mean(ev**2))),
        "n":      len(eh),
    }

s2 = stats(p2_errors_h, p2_errors_v)
s3 = stats(p3_errors_h, p3_errors_v)

print("Phase 2:", s2)
print("Phase 3:", s3)
print()

# =============================================================================
# Plot 1 — Side-by-side scatter comparison Phase 2 vs Phase 3
# =============================================================================
fig, axes = plt.subplots(1, 2, figsize=(14, 7))
fig.suptitle(
    "SPP Position Scatter — FRDN\nPhase 2 vs Phase 3 comparison",
    fontsize=13
)

theta = np.linspace(0, 2 * np.pi, 300)

for ax, ne, ee, eh, ev, s, label, color_dot, color_cep50, color_cep95 in [
    (
        axes[0],
        p2_north_errors, p2_east_errors, p2_errors_h, p2_errors_v, s2,
        "Phase 2\n(no iono, no weighting, first ephemeris)",
        "#185FA5", "#1D9E75", "#D85A30"
    ),
    (
        axes[1],
        p3_north_errors, p3_east_errors, p3_errors_h, p3_errors_v, s3,
        "Phase 3\n(Klobuchar + weighting + closest ephemeris)",
        "#534AB7", "#1D9E75", "#D85A30"
    ),
]:
    ax.scatter(ee, ne, s=5, alpha=0.4, color=color_dot,
               label=f"SPP epochs (n={s['n']})")
    ax.plot(0, 0, "r+", markersize=14, markeredgewidth=2.5,
            label="FRDN reference (NRCan)", zorder=5)

    ax.plot(s["cep50"] * np.cos(theta), s["cep50"] * np.sin(theta),
            color=color_cep50, linewidth=1.8, linestyle="--",
            label=f"CEP50 = {s['cep50']:.1f} m")
    ax.plot(s["cep95"] * np.cos(theta), s["cep95"] * np.sin(theta),
            color=color_cep95, linewidth=1.8, linestyle="--",
            label=f"CEP95 = {s['cep95']:.1f} m")

    ax.set_xlabel("East error (m)", fontsize=11)
    ax.set_ylabel("North error (m)", fontsize=11)
    ax.set_title(label, fontsize=10)
    ax.legend(fontsize=8)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    ax.axhline(0, color="gray", linewidth=0.4, alpha=0.4)
    ax.axvline(0, color="gray", linewidth=0.4, alpha=0.4)

    # Force same axis limits for fair comparison
    lim = max(
        np.max(np.abs(p2_north_errors)), np.max(np.abs(p2_east_errors)),
        np.max(np.abs(p3_north_errors)), np.max(np.abs(p3_east_errors))
    ) * 1.1
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)

plt.tight_layout()
out = "outputs/plots/phase3_scatter_comparison.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out}")

# =============================================================================
# Plot 2 — Error time series Phase 3
# =============================================================================
epochs_min = np.arange(len(p3_errors_h)) * 30 / 60

fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True)
fig.suptitle("SPP Position Error Time Series — FRDN (Phase 3)", fontsize=13)

axes[0].plot(epochs_min, p3_errors_h, color="#534AB7",
             linewidth=0.8, label="Phase 3 horizontal error")
axes[0].plot(epochs_min, p2_errors_h[:len(p3_errors_h)],
             color="#185FA5", linewidth=0.6, alpha=0.5,
             linestyle="--", label="Phase 2 horizontal error")
axes[0].axhline(s3["cep50"], color="#1D9E75", linestyle="--",
                linewidth=1.0, label=f"Phase 3 CEP50 = {s3['cep50']:.1f} m")
axes[0].axhline(s2["cep50"], color="#1D9E75", linestyle=":",
                linewidth=0.8, alpha=0.6,
                label=f"Phase 2 CEP50 = {s2['cep50']:.1f} m")
axes[0].set_ylabel("Horizontal error (m)", fontsize=11)
axes[0].legend(fontsize=8)
axes[0].grid(True, alpha=0.3)
axes[0].set_ylim(bottom=0)

axes[1].plot(epochs_min, p3_errors_v, color="#D85A30",
             linewidth=0.8, label="Phase 3 vertical error")
axes[1].axhline(s3["rmse_v"], color="#993C1D", linestyle="--",
                linewidth=1.0, label=f"RMSE_V = {s3['rmse_v']:.1f} m")
axes[1].set_ylabel("Vertical error (m)", fontsize=11)
axes[1].set_xlabel("Time (minutes from session start)", fontsize=11)
axes[1].legend(fontsize=8)
axes[1].grid(True, alpha=0.3)
axes[1].set_ylim(bottom=0)

plt.tight_layout()
out = "outputs/plots/phase3_error_timeseries.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out}")

# =============================================================================
# Plot 3 — Accuracy improvement bar chart
# =============================================================================
metrics      = ["CEP50", "CEP95", "RMSE_H", "RMSE_V"]
p2_vals      = [s2["cep50"], s2["cep95"], s2["rmse_h"], s2["rmse_v"]]
p3_vals      = [s3["cep50"], s3["cep95"], s3["rmse_h"], s3["rmse_v"]]
improvements = [(1 - p3/p2)*100 for p2, p3 in zip(p2_vals, p3_vals)]

x   = np.arange(len(metrics))
w   = 0.35
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
fig.suptitle("Phase 2 vs Phase 3 Accuracy Comparison — FRDN", fontsize=13)

bars2 = axes[0].bar(x - w/2, p2_vals, w, label="Phase 2",
                    color="#185FA5", alpha=0.8, edgecolor="white")
bars3 = axes[0].bar(x + w/2, p3_vals, w, label="Phase 3",
                    color="#534AB7", alpha=0.8, edgecolor="white")

for bar, val in zip(bars2, p2_vals):
    axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                f"{val:.1f}", ha="center", fontsize=8, color="#185FA5")
for bar, val in zip(bars3, p3_vals):
    axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                f"{val:.1f}", ha="center", fontsize=8, color="#534AB7")

axes[0].set_xticks(x)
axes[0].set_xticklabels(metrics)
axes[0].set_ylabel("Error (m)", fontsize=11)
axes[0].set_title("Absolute accuracy metrics", fontsize=11)
axes[0].legend(fontsize=9)
axes[0].grid(True, alpha=0.3, axis="y")

colors_imp = ["#1D9E75" if i > 0 else "#D85A30" for i in improvements]
bars_imp   = axes[1].bar(metrics, improvements, color=colors_imp,
                         edgecolor="white", alpha=0.85)
for bar, imp in zip(bars_imp, improvements):
    axes[1].text(bar.get_x() + bar.get_width()/2,
                bar.get_height() + 0.3 if imp >= 0 else bar.get_height() - 1.5,
                f"{imp:.1f}%", ha="center", fontsize=9,
                color="#0F6E56" if imp > 0 else "#993C1D")

axes[1].axhline(0, color="gray", linewidth=0.8)
axes[1].set_ylabel("Improvement (%)", fontsize=11)
axes[1].set_title("Percentage improvement Phase 2 → Phase 3", fontsize=11)
axes[1].grid(True, alpha=0.3, axis="y")

plt.tight_layout()
out = "outputs/plots/phase3_accuracy_comparison.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out}")

# =============================================================================
# Plot 4 — Error distribution comparison
# =============================================================================
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
fig.suptitle("SPP Error Distribution Comparison — FRDN", fontsize=13)

axes[0].hist(p2_errors_h, bins=25, alpha=0.6, color="#185FA5",
             edgecolor="white", label=f"Phase 2 (CEP50={s2['cep50']:.1f} m)")
axes[0].hist(p3_errors_h, bins=25, alpha=0.6, color="#534AB7",
             edgecolor="white", label=f"Phase 3 (CEP50={s3['cep50']:.1f} m)")
axes[0].axvline(s2["cep50"], color="#185FA5", linestyle="--", linewidth=1.5)
axes[0].axvline(s3["cep50"], color="#534AB7", linestyle="--", linewidth=1.5)
axes[0].set_xlabel("Horizontal error (m)", fontsize=11)
axes[0].set_ylabel("Epoch count", fontsize=11)
axes[0].set_title("Horizontal error distribution", fontsize=11)
axes[0].legend(fontsize=9)
axes[0].grid(True, alpha=0.3)

axes[1].hist(p2_errors_v, bins=25, alpha=0.6, color="#185FA5",
             edgecolor="white", label=f"Phase 2 (RMSE={s2['rmse_v']:.1f} m)")
axes[1].hist(p3_errors_v, bins=25, alpha=0.6, color="#534AB7",
             edgecolor="white", label=f"Phase 3 (RMSE={s3['rmse_v']:.1f} m)")
axes[1].set_xlabel("Vertical error (m)", fontsize=11)
axes[1].set_ylabel("Epoch count", fontsize=11)
axes[1].set_title("Vertical error distribution", fontsize=11)
axes[1].legend(fontsize=9)
axes[1].grid(True, alpha=0.3)

plt.tight_layout()
out = "outputs/plots/phase3_error_distribution.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out}")

# =============================================================================
# Final printed summary report
# =============================================================================
cep_imp  = (1 - s3["cep50"]  / s2["cep50"])  * 100
rmse_imp = (1 - s3["rmse_h"] / s2["rmse_h"]) * 100

print()
print("=" * 60)
print("PHASE 3 FINAL SUMMARY REPORT — FRDN")
print("=" * 60)
print(f"  Station:          FRDN — Fredericton, New Brunswick")
print(f"  Session:          2025-06-01 00:00–02:00 UTC")
print(f"  Epochs:           {s3['n']} (30-second sampling)")
print(f"  Constellation:    GPS only")
print()
print("  Corrections applied:")
print("    Satellite clock:      broadcast ephemeris (af0/af1/af2)")
print("    Relativistic:         orbital mechanics model")
print("    Ionosphere:           Klobuchar 8-coefficient model")
print("    Troposphere:          simplified Hopfield model")
print("    Satellite weighting:  SNR + CMC combined quality flags")
print("    Ephemeris selection:  closest Toe to observation epoch")
print()
print(f"  {'Metric':<20} {'Phase 2':>10} {'Phase 3':>10} {'Improvement':>12}")
print(f"  {'-'*56}")
rows = [
    ("CEP50 (m)",  s2["cep50"],  s3["cep50"]),
    ("CEP95 (m)",  s2["cep95"],  s3["cep95"]),
    ("RMSE_H (m)", s2["rmse_h"], s3["rmse_h"]),
    ("RMSE_V (m)", s2["rmse_v"], s3["rmse_v"]),
]
for label, v2, v3 in rows:
    imp = (1 - v3/v2) * 100
    arrow = "↓" if imp > 0 else "↑"
    print(f"  {label:<20} {v2:>10.1f} {v3:>10.1f} {arrow}{abs(imp):>9.1f}%")
print()
print(f"  Signal quality (SNR + CMC):")
print(f"    Clean satellites:     10")
print(f"    Suspect satellites:   3")
print(f"    Multipath satellites: 0")
print()
print(f"  Overall CEP50 improvement: {cep_imp:.1f}%")
print(f"  Overall RMSE_H improvement: {rmse_imp:.1f}%")
print("=" * 60)
print()
print("All plots saved to outputs/plots/")