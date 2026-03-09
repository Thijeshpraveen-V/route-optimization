# Module 2 — Forward + Reverse Logistics Network
# Extends Layer 1 (14 delivery stops) with 3 return pickup stops

# (id, name, lat, lon, zone, stop_type)
ALL_LOCS_M2 = [
    (0,  "Koramangala Hub",       12.9352, 77.6245, "DEPOT", "DEPOT"),
    # ── Delivery stops (outbound) ───────────────────────────────────────────
    (1,  "Jayanagar 4th Block",   12.9250, 77.5938, "A",  "DELIVERY"),
    (2,  "Jayanagar 3rd Block",   12.9220, 77.5801, "A",  "DELIVERY"),
    (3,  "Lalbagh West Gate",     12.9507, 77.5848, "A",  "DELIVERY"),
    (4,  "BTM 1st Stage",         12.9166, 77.6101, "A",  "DELIVERY"),
    (5,  "HSR Layout Sec 1",      12.9116, 77.6389, "B",  "DELIVERY"),
    (6,  "HSR Layout Sec 7",      12.9082, 77.6483, "B",  "DELIVERY"),
    (7,  "Bellandur Signal",      12.9257, 77.6664, "B",  "DELIVERY"),
    (8,  "Sarjapur Road",         12.9021, 77.6737, "B",  "DELIVERY"),
    (9,  "Silk Board Jn",         12.9166, 77.6243, "C",  "DELIVERY"),
    (10, "Ecity Phase 1",         12.8458, 77.6603, "C",  "DELIVERY"),
    (11, "Ecity Phase 2",         12.8392, 77.6764, "C",  "DELIVERY"),
    (12, "Hebbagodi",             12.8221, 77.6808, "C",  "DELIVERY"),
    (13, "Indiranagar 100ft",     12.9784, 77.6408, "D",  "DELIVERY"),
    (14, "Whitefield Main Rd",    12.9698, 77.7499, "D",  "DELIVERY"),
    # ── Return pickup stops (inbound) ───────────────────────────────────────
    # Co-located near delivery zones so vehicles combine on same loop
    (15, "Koramangala 2nd Block", 12.9312, 77.6189, "A",  "PICKUP"),
    (16, "HSR Layout Sector 3",   12.9053, 77.6431, "B",  "PICKUP"),
    (17, "Agara Lake Road",       12.9161, 77.6317, "B",  "PICKUP"),
]

# (order_id, stop_id, stop_type, demand_units, tw_start_min, tw_end_min, priority)
ORDERS_M2 = [
    # ── Delivery orders ──────────────────────────────────────────────────────
    ("O01",  1, "DELIVERY", 2,   0,  60, "MEDIUM"),
    ("O02",  2, "DELIVERY", 1,   0,  60, "MEDIUM"),
    ("O03",  3, "DELIVERY", 2,  60, 120, "LOW"),
    ("O04",  4, "DELIVERY", 1,  60, 120, "MEDIUM"),
    ("O05",  5, "DELIVERY", 2, 120, 180, "MEDIUM"),
    ("O06",  6, "DELIVERY", 1, 120, 180, "LOW"),
    ("O07",  7, "DELIVERY", 2, 120, 180, "MEDIUM"),
    ("O08",  8, "DELIVERY", 1, 120, 180, "LOW"),
    ("O09",  9, "DELIVERY", 1,   0,  35, "HIGH"),
    ("O10", 10, "DELIVERY", 2,  45,  85, "HIGH"),
    ("O11", 11, "DELIVERY", 1,  90, 130, "MEDIUM"),
    ("O12", 12, "DELIVERY", 1, 135, 175, "LOW"),
    ("O13", 13, "DELIVERY", 2,   0,  45, "HIGH"),
    ("O14", 14, "DELIVERY", 1,   0, 240, "LOW"),
    # ── Return pickup orders ─────────────────────────────────────────────────
    # Wide time windows — customer is home all morning to hand off return
    ("R01", 15, "PICKUP",   2,  60, 180, "MEDIUM"),
    ("R02", 16, "PICKUP",   2, 120, 240, "MEDIUM"),
    ("R03", 17, "PICKUP",   1,  60, 240, "LOW"),
]

# 4 vehicles — slightly larger cap (7) to handle mixed delivery+pickup loads
VEHICLES_M2 = [("V01", 7), ("V02", 7), ("V03", 7), ("V04", 7)]

PRIORITY_PENALTY_M2 = {"HIGH": 500, "MEDIUM": 150, "LOW": 50}
COST_PER_KM_M2      = 12
SPEED_KMH_M2        = 25
