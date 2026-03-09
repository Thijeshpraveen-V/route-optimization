import math
import json
import os
import urllib.request
from layer1.data.network import ALL_LOCS, SPEED_KMH


def haversine_m(lat1, lon1, lat2, lon2):
    """Straight-line distance in meters."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi    = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def build_fallback_matrices():
    """
    Haversine × 1.35 urban road factor.
    1.35 is the empirical road-to-crow-fly ratio for Bengaluru urban grid.
    Time = distance / (25 km/h average urban speed).
    """
    n   = len(ALL_LOCS)
    dist  = [[0]*n for _ in range(n)]
    time_ = [[0]*n for _ in range(n)]
    spd   = SPEED_KMH * 1000 / 3600  # m/s

    for i in range(n):
        for j in range(n):
            if i != j:
                d = haversine_m(
                    ALL_LOCS[i][2], ALL_LOCS[i][3],
                    ALL_LOCS[j][2], ALL_LOCS[j][3]
                ) * 1.35                        # road factor
                dist[i][j]  = int(d)
                time_[i][j] = int(d / spd)     # seconds
    return dist, time_


def fetch_osrm_matrices():
    """
    Fetch real road distances + durations from OSRM public API.
    Returns (dist_meters, duration_seconds) matrices.
    """
    coords = ";".join(
        f"{loc[3]},{loc[2]}" for loc in ALL_LOCS   # OSRM: lon,lat
    )
    url = (
        f"http://router.project-osrm.org/table/v1/driving/{coords}"
        f"?annotations=duration,distance"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "BLRRouteOptimizer/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())

    if data.get("code") != "Ok":
        raise ValueError(f"OSRM API error: {data.get('message')}")

    dist  = [[int(v or 0) for v in row] for row in data["distances"]]
    time_ = [[int(v or 0) for v in row] for row in data["durations"]]
    return dist, time_


def get_matrices(cache_path="layer1/data/distance_matrix.json"):
    """
    Primary: load from cache.
    Secondary: fetch from OSRM and cache.
    Fallback: Haversine × 1.35.
    """
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)

    # ── Load from cache ──────────────────────────────────────────────
    if os.path.exists(cache_path):
        print(f"✅ Loaded distance matrix from cache ({cache_path})")
        with open(cache_path) as f:
            cached = json.load(f)
        return cached["dist"], cached["time_"]

    # ── Try OSRM ─────────────────────────────────────────────────────
    try:
        print("🌐 Fetching real road distances from OSRM…")
        dist, time_ = fetch_osrm_matrices()
        source = "OSRM"
        print(f"✅ OSRM matrix fetched ({len(ALL_LOCS)}×{len(ALL_LOCS)})")
    except Exception as e:
        print(f"⚠️  OSRM unavailable ({e}). Falling back to Haversine × 1.35")
        dist, time_ = build_fallback_matrices()
        source = "Haversine×1.35"

    # ── Cache for future runs (demo runs fully offline) ───────────────
    with open(cache_path, "w") as f:
        json.dump({"dist": dist, "time_": time_, "source": source}, f)
    print(f"💾 Matrix cached → {cache_path} (future runs are offline)")

    return dist, time_
