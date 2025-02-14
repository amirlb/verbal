import math


base_coords = (-11, 11)
center = (12, 12)

for i in range(8):
    if i % 2 == 1:
        theta = i * math.tau / 16
        x = center[0] + math.cos(theta) * base_coords[0]
        y = center[1] + math.sin(theta) * base_coords[0]
        print(f"M{x:.5} {y:.5}", end=" ")
        x = center[0] + math.cos(theta) * base_coords[1]
        y = center[1] + math.sin(theta) * base_coords[1]
        print(f"L{x:.5} {y:.5}", end=" ")
