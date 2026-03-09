# Exponential Moving Average correction table for travel time prediction

import json, os
from layer1.data.network import ALL_LOCS

SAVE_PATH  = "layer3/data/eta_corrections.json"
TIME_BANDS = {
    "EARLY": (0,   60),   # 8:00–9:00 AM
    "MID":   (60, 120),   # 9:00–10:00 AM
    "LATE":  (120, 300),  # 10:00 AM onward
}

def get_time_band(arrival_min: int) -> str:
    for band, (s, e) in TIME_BANDS.items():
        if s <= arrival_min < e:
            return band
    return "LATE"


class ETALearner:
    """
    Stores per-segment, per-time-band delay correction factors.
    Uses Exponential Moving Average (EMA) to update after each delivery round.

    Factor > 1.0 → segment is systematically slower than OSRM predicted
    Factor < 1.0 → segment is faster
    """

    def __init__(self, alpha: float = 0.3):
        self.alpha   = alpha        # EMA learning rate
        self.factors = {}           # "i_j_band" → float
        self.counts  = {}           # "i_j_band" → int (observation count)
        self.history = []           # round-level metrics

    def _key(self, i, j, band): return f"{i}_{j}_{band}"

    def get_factor(self, i: int, j: int, band: str) -> float:
        return self.factors.get(self._key(i, j, band), 1.0)

    def apply_to_matrix(self, base_time_matrix: list) -> list:
        """
        Returns a corrected copy of the time matrix.
        Uses average correction factor across all time bands per segment.
        """
        n = len(base_time_matrix)
        corrected = [row[:] for row in base_time_matrix]

        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                band_factors = [
                    self.factors[self._key(i, j, b)]
                    for b in TIME_BANDS
                    if self._key(i, j, b) in self.factors
                ]
                if band_factors:
                    avg_f = sum(band_factors) / len(band_factors)
                    corrected[i][j] = int(base_time_matrix[i][j] * avg_f)
        return corrected

    def record_observations(self, observations: list) -> float:
        """
        Updates EMA factors from delivery observations.
        Returns MAE (%) after update.
        """
        post_errors = []

        for obs in observations:
            i, j   = obs["from_node"], obs["to_node"]
            band   = obs["time_band"]
            base_s = obs["base_pred_s"]
            act_s  = obs["actual_s"]

            if base_s <= 0:
                continue

            obs_factor = act_s / base_s
            key = self._key(i, j, band)

            if key not in self.factors:
                self.factors[key] = obs_factor
            else:
                self.factors[key] = (
                    (1 - self.alpha) * self.factors[key]
                    + self.alpha * obs_factor
                )
            self.counts[key] = self.counts.get(key, 0) + 1

            new_pred = base_s * self.factors[key]
            post_errors.append(abs(act_s - new_pred) / new_pred)

        mae_after = round(sum(post_errors) / len(post_errors) * 100, 1) if post_errors else 0.0
        return mae_after

    def compute_mae(self, observations: list) -> float:
        """Computes MAE (%) BEFORE updating — pre-update error tracking."""
        errors = []
        for obs in observations:
            i, j   = obs["from_node"], obs["to_node"]
            band   = obs["time_band"]
            base_s = obs["base_pred_s"]
            act_s  = obs["actual_s"]
            if base_s <= 0:
                continue
            corr_pred = base_s * self.get_factor(i, j, band)
            errors.append(abs(act_s - corr_pred) / corr_pred)
        return round(sum(errors) / len(errors) * 100, 1) if errors else 0.0

    def get_top_corrections(self, n: int = 10) -> list:
        """Top n segments with highest learned delay factors."""
        items = []
        for key, factor in self.factors.items():
            parts = key.split("_")
            if len(parts) == 3:
                i, j, band = int(parts[0]), int(parts[1]), parts[2]
                items.append({
                    "from_node": i,
                    "to_node":   j,
                    "from_name": ALL_LOCS[i][1] if i < len(ALL_LOCS) else str(i),
                    "to_name":   ALL_LOCS[j][1] if j < len(ALL_LOCS) else str(j),
                    "band":      band,
                    "factor":    round(factor, 3),
                    "count":     self.counts.get(key, 0),
                    "impact":    "🔴 Severe"  if factor >= 1.4 else
                                 "🟠 Heavy"   if factor >= 1.2 else
                                 "🟡 Moderate",
                })
        return sorted(items, key=lambda x: -x["factor"])[:n]

    def save(self, path: str = SAVE_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({"factors": self.factors, "counts": self.counts,
                       "history": self.history}, f, indent=2)

    def load(self, path: str = SAVE_PATH):
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            self.factors = data.get("factors", {})
            self.counts  = data.get("counts",  {})
            self.history = data.get("history", [])
