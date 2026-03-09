# All static network data for the Bengaluru delivery demo

# (id, name, lat, lon, zone)
ALL_LOCS = [
    (0,  "Koramangala Hub",      12.9352, 77.6245, "DEPOT"),
    # Zone A — South Cluster (tight geographic area, ~2km radius)
    # Designed failure: naive sends 4 vehicles, optimizer sends 1
    (1,  "Jayanagar 4th Block",  12.9250, 77.5938, "A"),
    (2,  "Jayanagar 3rd Block",  12.9220, 77.5801, "A"),
    (3,  "Lalbagh West Gate",    12.9507, 77.5848, "A"),
    (4,  "BTM 1st Stage",        12.9166, 77.6101, "A"),
    # Zone B — East Cluster (HSR area, ~2km radius)
    # Designed failure: naive zig-zags between zones
    (5,  "HSR Layout Sec 1",     12.9116, 77.6389, "B"),
    (6,  "HSR Layout Sec 7",     12.9082, 77.6483, "B"),
    (7,  "Bellandur Signal",     12.9257, 77.6664, "B"),
    (8,  "Sarjapur Road",        12.9021, 77.6737, "B"),
    # Zone C — Hosur Road Corridor (linear, 10km stretch)
    # Designed failure: tight sequential windows naive will breach
    (9,  "Silk Board Jn",        12.9166, 77.6243, "C"),
    (10, "Ecity Phase 1",        12.8458, 77.6603, "C"),
    (11, "Ecity Phase 2",        12.8392, 77.6764, "C"),
    (12, "Hebbagodi",            12.8221, 77.6808, "C"),
    # Zone D — Priority Trap (far outliers with conflicting priorities)
    # Designed failure: naive routes LOW-priority first (closer),
    # misses HIGH-priority tight window
    (13, "Indiranagar 100ft",    12.9784, 77.6408, "D"),
    (14, "Whitefield Main Rd",   12.9698, 77.7499, "D"),
]

# (order_id, stop_id, priority, demand, tw_start_min, tw_end_min)
# All times in minutes from 8:00 AM (working day start)
ORDERS = [
    # Zone A — two batches: early morning + mid morning
    ("O01", 1,  "MEDIUM", 2,   0,  60),   # 8:00–9:00 AM  — tight
    ("O02", 2,  "MEDIUM", 1,   0,  60),   # 8:00–9:00 AM  — tight (same window as O01 → must batch)
    ("O03", 3,  "LOW",    2,  60, 120),   # 9:00–10:00 AM — different band than O01/O02
    ("O04", 4,  "MEDIUM", 1,  60, 120),   # 9:00–10:00 AM — same band as O03

    # Zone B — afternoon band, must be served together
    ("O05", 5,  "MEDIUM", 2, 120, 180),   # 10:00–11:00 AM
    ("O06", 6,  "LOW",    1, 120, 180),   # 10:00–11:00 AM
    ("O07", 7,  "MEDIUM", 2, 120, 180),   # 10:00–11:00 AM
    ("O08", 8,  "LOW",    1, 120, 180),   # 10:00–11:00 AM

    # Zone C — TIGHT SEQUENTIAL windows on Hosur corridor
    # Each window opens AFTER the previous closes → FORCES correct order
    # Naive NN violates 3/4 of these by arriving wrong time
    ("O09", 9,  "HIGH",   1,   0,  35),   # Silk Board:  8:00–8:35 → must be FIRST
    ("O10", 10, "HIGH",   2,  45,  85),   # Ecity Ph1:   8:45–9:25 → must follow Silk Board
    ("O11", 11, "MEDIUM", 1,  90, 130),   # Ecity Ph2:   9:30–10:10
    ("O12", 12, "LOW",    1, 135, 175),   # Hebbagodi:   10:15–10:55 → must be LAST

    # Zone D — Priority trap
    ("O13", 13, "HIGH",   2,   0,  45),   # Indiranagar: 8:00–8:45 HIGH, tight
    ("O14", 14, "LOW",    1,   0, 240),   # Whitefield:  8:00–12:00 open
]

# (vehicle_id, capacity_units)
VEHICLES = [("V01", 5), ("V02", 5), ("V03", 5), ("V04", 5)]

# Cost model
PRIORITY_PENALTY_PER_MIN = {"HIGH": 500, "MEDIUM": 150, "LOW": 50}
COST_PER_KM  = 12    # ₹/km (fuel + driver, Bengaluru avg)
SPEED_KMH    = 25    # urban Bengaluru average
