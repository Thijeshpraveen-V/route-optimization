"""module2/run_module2.py — Standalone validation script for Module 2."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from module2.src.matrices_m2     import get_matrices_m2
from module2.src.naive_solver_m2 import solve_naive_m2
from module2.src.optimizer_m2    import solve_vrptw_m2
from module2.src.metrics_m2      import compute_sla_m2, print_report_m2

if __name__ == "__main__":
    print("🔧 Building M2 distance/time matrices (18×18)…")
    dist, time_ = get_matrices_m2()

    print("🔄 Running Naive M2 — siloed delivery + pickup fleets…")
    naive  = solve_naive_m2(dist, time_)
    n_sla  = compute_sla_m2(naive, time_, use_solver_times=False)
    print(f"   → {naive['n_veh']} vehicles  "
          f"({naive['delivery_vehicles']} delivery + {naive['pickup_vehicles']} pickup)  "
          f"| {naive['total_km']:.1f} km  | SLA {n_sla['sla_pct']}%")

    print("🤖 Running AI Unified Fleet (OR-Tools VRPTW)…")
    opt = solve_vrptw_m2(dist, time_)
    if not opt:
        print("❌ No solution found — check capacity or TW data.")
        sys.exit(1)

    o_sla = compute_sla_m2(opt, time_, use_solver_times=True)
    print(f"   → {opt['n_veh']} vehicles (mixed)  "
          f"| {opt['total_km']:.1f} km  | SLA {o_sla['sla_pct']}%")

    print_report_m2(naive, opt, n_sla, o_sla)

    # Save for frontend
    out = {
        "naive": {**naive, "sla": n_sla},
        "opt": {
            **opt,
            "sla": o_sla,
            "routes": [
                {k: r[k] for k in ("vehicle", "route_wt", "dist_m", "time_s",
                                   "n_deliveries", "n_pickups")}
                for r in opt["routes"]
            ],
        },
    }
    with open("module2_output.json", "w") as f:
        json.dump(out, f, indent=2)
    print("💾 module2_output.json saved.")
