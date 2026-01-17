"""ZE QIN'S SCROLLING DATA"""

import statistics

data = [
    4.85,
    3.28,
    0.93,
    1.96,
    0.68,
    0.90,
    1.21,
    7.78,
    5.01,
    4.80,
    4.81,
    2.83,
    16.88,
    2.68,
    9.04,
    1.04,
    1.61,
    1.84,
    1.63,
    1.71,
    1.96,
    2.09
]

print(f"Sample size: {len(data)}")
print(f"Average: {sum(data)/len(data):.2f}s")
print(f"Max: {max(data)}s")
print(f"Min: {min(data)}s")
std_dev = statistics.stdev(data)
print(f"Sample Standard Deviation: {std_dev:.2f}s")

# Population standard deviation
population_std_dev = statistics.pstdev(data)
print(f"Population Standard Deviation: {population_std_dev:.2f}s")