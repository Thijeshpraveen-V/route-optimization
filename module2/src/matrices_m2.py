"""module2/src/matrices_m2.py — 18×18 OSRM matrix builder with cache."""
import math, json, os, urllib.request
from module2.data.network_m2 import ALL_LOCS_M2, SPEED_KMH_M2

CACHE = "module2/data/distance_matrix_m2.json"


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) *
         math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _build_fallback(locs):
    n   = len(locs)
    spd = SPEED_KMH_M2 * 1000 / 3600
    d = [[0] * n for _ in range(n)]
    t = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                dist    = haversine_m(locs[i][2], locs[i][3], locs[j][2], locs[j][3]) * 1.35
                d[i][j] = int(dist)
                t[i][j] = int(dist / spd)
    return d, t


def _fetch_osrm(locs):
    coords = ";".join(f"{l[3]},{l[2]}" for l in locs)
    url    = (f"http://router.project-osrm.org/table/v1/driving/{coords}"
              f"?annotations=duration,distance")
    req    = urllib.request.Request(url, headers={"User-Agent": "M2RouteOpt/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.loads(r.read())
    if data.get("code") != "Ok":
        raise ValueError(data.get("message", "OSRM error"))
    return (
        [[int(v or 0) for v in row] for row in data["distances"]],
        [[int(v or 0) for v in row] for row in data["durations"]],
    )


def get_matrices_m2():
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    if os.path.exists(CACHE):
        print("✅ M2 matrix loaded from cache")
        with open(CACHE) as f:
            c = json.load(f)
        return c["dist"], c["time_"]
    try:
        print("🌐 Fetching OSRM for M2 (18×18)…")
        dist, time_ = _fetch_osrm(ALL_LOCS_M2)
        src = "OSRM"
    except Exception as e:
        print(f"⚠️  OSRM failed ({e}). Using Haversine×1.35 fallback")
        dist, time_ = _build_fallback(ALL_LOCS_M2)
        src = "Haversine"
    with open(CACHE, "w") as f:
        json.dump({"dist": dist, "time_": time_, "source": src}, f)
    print(f"💾 M2 matrix cached ({src})")
    return dist, time_
