from src.gnss_pipeline.accuracy import compute_position_error, compute_accuracy_statistics

# Test 1: position error at FRDN
# Use your SPP result from test_phase2.py
error = compute_position_error(
    computed_lat=45.933453,
    computed_lon=-66.659546,
    computed_height=105.18,
    ref_lat=45.9455,
    ref_lon=-66.6443,
    ref_height=24.0,
)

print("Position error for single epoch:")
print(f"  Horizontal: {error['horizontal_m']:.1f} m")
print(f"  Vertical:   {error['vertical_m']:.1f} m")
print(f"  North:      {error['north_m']:.1f} m")
print(f"  East:       {error['east_m']:.1f} m")

# Test 2: accuracy statistics with known values
stats = compute_accuracy_statistics(
    errors_horizontal=[3.0, 4.0, 2.0, 5.0, 3.5],
    errors_vertical=[8.0, 9.0, 7.0, 10.0, 8.5],
)

print("\nAccuracy statistics test:")
for k, v in stats.items():
    print(f"  {k}: {v}")

if stats["CEP50"] < stats["CEP95"]:
    print("\nPASS — CEP50 < CEP95 as expected")
else:
    print("\nFAIL — CEP50 should be less than CEP95")