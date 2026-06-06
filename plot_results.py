"""
Phase 2 visualization — generates three plots from processed session data.
Run from project root after process_session.py has been executed.
"""
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path

# Load saved results
errors_h    = np.load("data/processed/errors_h.npy")
errors_v    = np.load("data/processed/errors_v.npy")
north_errors = np.load("data/processed/north_errors.npy")
east_errors  = np.load("data/processed/east_errors.npy")

Path("outputs/plots").mkdir(parents=True, exist_ok=True)

# Accuracy statistics
cep50 = float(np.percentile(errors_h, 50))
cep95 = float(np.percentile(errors_h, 95))
rmse_h = float(np.sqrt(np.mean(errors_h**2)))
rmse_v = float(np.sqrt(np.mean(errors_v**2)))
n = len(errors_h)

print(f"Generating plots for {n} epochs...")
print(f"CEP50={cep50:.1f} m  CEP95={cep95:.1f} m  RMSE_H={rmse_h:.1f} m")

# ── Plot 1: Position scatter ──────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(7, 7))

ax.scatter(east_errors, north_errors,
           s=6, alpha=0.5, color="#185FA5",
           label=f"SPP epochs (n={n})")

ax.plot(0, 0, "r+", markersize=14, markeredgewidth=2.5,
        label="FRDN reference (NRCan)", zorder=5)

theta = np.linspace(0, 2 * np.pi, 300)
ax.plot(cep50 * np.cos(theta), cep50 * np.sin(theta),
        color="#1D9E75", linewidth=1.8, linestyle="--",
        label=f"CEP50 = {cep50:.1f} m")
ax.plot(cep95 * np.cos(theta), cep95 * np.sin(theta),
        color="#D85A30", linewidth=1.8, linestyle="--",
        label=f"CEP95 = {cep95:.1f} m")

ax.set_xlabel("East error (m)", fontsize=12)
ax.set_ylabel("North error (m)", fontsize=12)
ax.set_title("SPP Position Scatter — FRDN\n(GPS only, no ionospheric correction)",
             fontsize=13)
ax.legend(fontsize=10)
ax.set_aspect("equal")
ax.grid(True, alpha=0.3)
ax.axhline(0, color="gray", linewidth=0.5, alpha=0.5)
ax.axvline(0, color="gray", linewidth=0.5, alpha=0.5)

plt.tight_layout()
out1 = "outputs/plots/position_scatter_FRDN.png"
plt.savefig(out1, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out1}")

# ── Plot 2: Error time series ─────────────────────────────────────────────────
epochs_axis = np.arange(n) * 30 / 60  # convert to minutes

fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
fig.suptitle("SPP Position Error Time Series — FRDN", fontsize=13)

axes[0].plot(epochs_axis, errors_h,
             color="#1D9E75", linewidth=0.8, label="Horizontal error")
axes[0].axhline(cep50, color="#0F6E56", linestyle="--", linewidth=1.0,
                label=f"CEP50 = {cep50:.1f} m")
axes[0].axhline(rmse_h, color="#085041", linestyle=":", linewidth=1.0,
                label=f"RMSE = {rmse_h:.1f} m")
axes[0].set_ylabel("Horizontal error (m)", fontsize=11)
axes[0].legend(fontsize=9)
axes[0].grid(True, alpha=0.3)
axes[0].set_ylim(bottom=0)

axes[1].plot(epochs_axis, errors_v,
             color="#378ADD", linewidth=0.8, label="Vertical error")
axes[1].axhline(rmse_v, color="#185FA5", linestyle="--", linewidth=1.0,
                label=f"RMSE = {rmse_v:.1f} m")
axes[1].set_ylabel("Vertical error (m)", fontsize=11)
axes[1].set_xlabel("Time (minutes from session start)", fontsize=11)
axes[1].legend(fontsize=9)
axes[1].grid(True, alpha=0.3)
axes[1].set_ylim(bottom=0)

plt.tight_layout()
out2 = "outputs/plots/position_error_timeseries_FRDN.png"
plt.savefig(out2, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out2}")

# ── Plot 3: Error distribution histogram ─────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(12, 5))
fig.suptitle("SPP Error Distribution — FRDN", fontsize=13)

axes[0].hist(errors_h, bins=30, color="#185FA5", alpha=0.7, edgecolor="white")
axes[0].axvline(cep50, color="#1D9E75", linestyle="--", linewidth=1.5,
                label=f"CEP50 = {cep50:.1f} m")
axes[0].axvline(cep95, color="#D85A30", linestyle="--", linewidth=1.5,
                label=f"CEP95 = {cep95:.1f} m")
axes[0].set_xlabel("Horizontal error (m)", fontsize=11)
axes[0].set_ylabel("Epoch count", fontsize=11)
axes[0].set_title("Horizontal error distribution", fontsize=11)
axes[0].legend(fontsize=9)
axes[0].grid(True, alpha=0.3)

axes[1].hist(errors_v, bins=30, color="#378ADD", alpha=0.7, edgecolor="white")
axes[1].axvline(float(np.percentile(errors_v, 50)),
                color="#1D9E75", linestyle="--", linewidth=1.5,
                label=f"Median = {float(np.percentile(errors_v,50)):.1f} m")
axes[1].set_xlabel("Vertical error (m)", fontsize=11)
axes[1].set_ylabel("Epoch count", fontsize=11)
axes[1].set_title("Vertical error distribution", fontsize=11)
axes[1].legend(fontsize=9)
axes[1].grid(True, alpha=0.3)

plt.tight_layout()
out3 = "outputs/plots/error_distribution_FRDN.png"
plt.savefig(out3, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out3}")

print()
print("All plots saved to outputs/plots/")
print("Phase 2 visualization complete.")