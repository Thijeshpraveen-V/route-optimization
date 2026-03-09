# layer2/src/traffic_engine.py
# Bengaluru mock traffic events and congested matrix generator

import json

# ─── Node ID reference (from Layer 1 network) ────────────────────────────────
# 0=Depot, 1=Jayanagar4, 2=Jayanagar3, 3=Lalbagh, 4=BTM,
# 5=HSR1, 6=HSR7, 7=Bellandur, 8=Sarjapur,
# 9=SilkBoard, 10=EcityPh1, 11=EcityPh2, 12=Hebbagodi,
# 13=Indiranagar, 14=Whitefield

TRAFFIC_EVENTS = [
    {
        "id":          "EVT_001",
        "name":        "Silk Board + Hosur Road Morning Gridlock",
        "description": "Peak morning rush on NH-44 / Hosur Rd corridor. "
                       "Silk Board junction at standstill.",
        "trigger":     "8:00 – 10:00 AM",
        "type":        "RUSH_HOUR",
        "icon":        "🚦",
        "severity":    "HIGH",
        # segment (from, to): multiplier
        "segments": {
            (0,  9):  2.8,   # Depot → Silk Board
            (9,  0):  2.5,   # Silk Board → Depot
            (0, 10):  2.5,   # Depot → Ecity Ph1 (Hosur Rd direct)
            (10, 0):  2.3,
            (9, 10):  2.2,   # Silk Board → Ecity Ph1
            (10, 9):  2.0,
            (10, 11): 1.8,   # Ecity Ph1 → Ph2
            (11, 10): 1.8,
            (11, 12): 1.6,   # Ecity Ph2 → Hebbagodi
            (12, 11): 1.6,
            (4,  9):  1.7,   # BTM → Silk Board
            (9,  4):  1.7,
        },
    },
    {
        "id":          "EVT_002",
        "name":        "Sarjapur-Bellandur ORR Event Traffic",
        "description": "Public event on Outer Ring Road causing "
                       "heavy congestion on Sarjapur-Bellandur stretch.",
        "trigger":     "Event starts 9:00 AM",
        "type":        "EVENT",
        "icon":        "🎉",
        "severity":    "MEDIUM",
        "segments": {
            (0,  7):  2.2,   # Depot → Bellandur
            (7,  0):  2.0,
            (0,  8):  2.0,   # Depot → Sarjapur
            (8,  0):  1.8,
            (7,  8):  1.9,   # Bellandur ↔ Sarjapur
            (8,  7):  1.9,
            (5,  7):  1.6,   # HSR1 → Bellandur
            (7,  5):  1.5,
            (6,  8):  1.5,   # HSR7 → Sarjapur
        },
    },
    {
        "id":          "EVT_003",
        "name":        "Citywide Rain Delay",
        "description": "Heavy rain across Bengaluru causing 30% slowdown "
                       "on all road segments.",
        "trigger":     "Rain forecast from 10:00 AM",
        "type":        "WEATHER",
        "icon":        "🌧️",
        "severity":    "LOW",
        "segments":    "ALL",          # flag: multiply every segment
        "multiplier":  1.30,
    },
]


def apply_traffic(time_matrix: list, event: dict) -> list:
    """
    Returns a new time matrix with traffic multipliers applied for a given event.
    Does not modify the original matrix.
    """
    n = len(time_matrix)
    # Deep copy
    congested = [row[:] for row in time_matrix]

    if event["segments"] == "ALL":
        factor = event.get("multiplier", 1.0)
        for i in range(n):
            for j in range(n):
                if i != j:
                    congested[i][j] = int(congested[i][j] * factor)
    else:
        for (i, j), factor in event["segments"].items():
            if i < n and j < n:
                congested[i][j] = int(time_matrix[i][j] * factor)

    return congested


def apply_combined_events(time_matrix: list, selected_event_ids: list) -> list:
    """
    Applies multiple events simultaneously.
    Uses MAX multiplier when events overlap on the same segment.
    """
    n = len(time_matrix)
    congested = [row[:] for row in time_matrix]
    multipliers = [[1.0]*n for _ in range(n)]

    for event in TRAFFIC_EVENTS:
        if event["id"] not in selected_event_ids:
            continue
        if event["segments"] == "ALL":
            factor = event.get("multiplier", 1.0)
            for i in range(n):
                for j in range(n):
                    if i != j:
                        multipliers[i][j] = max(multipliers[i][j], factor)
        else:
            for (i, j), factor in event["segments"].items():
                if i < n and j < n:
                    multipliers[i][j] = max(multipliers[i][j], factor)

    for i in range(n):
        for j in range(n):
            if i != j:
                congested[i][j] = int(time_matrix[i][j] * multipliers[i][j])

    return congested


def get_segment_multipliers(selected_event_ids: list, n: int) -> list:
    """Returns the multiplier matrix for visualization (which segments are congested)."""
    m = [[1.0]*n for _ in range(n)]
    for event in TRAFFIC_EVENTS:
        if event["id"] not in selected_event_ids:
            continue
        if event["segments"] == "ALL":
            factor = event.get("multiplier", 1.0)
            for i in range(n):
                for j in range(n):
                    if i != j:
                        m[i][j] = max(m[i][j], factor)
        else:
            for (i, j), factor in event["segments"].items():
                if i < n and j < n:
                    m[i][j] = max(m[i][j], factor)
    return m
