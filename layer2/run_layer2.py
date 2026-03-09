# layer2/run_layer2.py
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from layer1.src.matrices        import get_matrices
from layer1.src.optimizer       import solve_vrptw
from layer2.src.traffic_engine  import TRAFFIC_EVENTS
from layer2.src.scenario_runner import run_all_scenarios


def sep(c="─", w=72): print(c * w)


if __name__ == "__main__":
    print("🔧 Loading matrices from cache…")
    dist, time_ = get_matrices()
    print("🚀 Running all 3 scenarios (Naive / AI / AI+Traffic)…\n")

    test_sets = [
        (["EVT_001"],              "EVT_001 only  (Hosur Rd Gridlock)"),
        (["EVT_002"],              "EVT_002 only  (ORR Event Traffic)"),
        (["EVT_003"],              "EVT_003 only  (Citywide Rain)"),
        (["EVT_001", "EVT_002"],   "EVT_001 + EVT_002  (Rush + Event)"),
        (["EVT_001", "EVT_002", "EVT_003"], "All 3 Events Combined"),
    ]

    all_results = {}

    for event_ids, label in test_sets:
        sep("═")
        print(f"  SCENARIO: {label}")
        sep("═")

        result = run_all_scenarios(dist, time_, event_ids)
        cmp    = result["comparison"]
        A, B, C = result["scenario_a"], result["scenario_b"], result["scenario_c"]

        print(f"\n  {'Metric':<28} {'A · Naive':>14} {'B · AI':>16} {'C · AI+Traffic':>16}")
        sep()
        rows = [
            ("Vehicles Used",    cmp["vehicles"]),
            ("Total Dist (km)",  [round(x, 1) for x in cmp["total_km"]]),
            ("SLA Compliance %", cmp["sla_pct"]),
            ("HIGH Breaches",    cmp["high_breach"]),
            ("Cost (₹)",         cmp["cost"]),
        ]
        for label_r, vals in rows:
            print(f"  {label_r:<28} {str(vals[0]):>14} {str(vals[1]):>16} {str(vals[2]):>16}")

        print(f"\n  ⏱  Time saved A→B: {abs(cmp['delay_b_vs_a'])} min")
        print(f"  ⏱  B→C improvement: {cmp['delay_saved_c_vs_b']} min")
        if cmp["stops_saved_by_rerouting"]:
            print(f"  ✅  Stops saved vs naive: {', '.join(cmp['stops_saved_by_rerouting'])}")
        else:
            print(f"  ℹ️  No additional stops to save vs naive")

        print(f"\n  🚦 Congested Segments (top 5):")
        for seg in result["congested_segs"][:5]:
            print(f"     {seg['from_name'][:18]} → {seg['to_name'][:18]}  {seg['severity']}  ×{seg['multiplier']}")

        all_results["+".join(event_ids)] = {
            "comparison": cmp,
            "active_events": [e["id"] for e in result["active_events"]],
        }

    # Save for frontend
    with open("layer2_output.json", "w") as f:
        json.dump(all_results, f, indent=2)
    sep("═")
    print("💾  layer2_output.json saved — frontend ready.")
    sep("═")
