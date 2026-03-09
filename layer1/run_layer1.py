import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from layer1.src.matrices  import get_matrices
from layer1.src.naive_solver import solve_naive
from layer1.src.optimizer    import solve_vrptw
from layer1.src.metrics      import compute_sla, print_report

if __name__ == "__main__":
    print("\n🔧 Building distance/time matrices…")
    dist, time_ = get_matrices()

    print("\n🔄 Running Naive Solver (Greedy Nearest Neighbour)…")
    naive = solve_naive(dist, time_)
    n_sla = compute_sla(naive, time_, use_solver_times=False)
    print(f"   → {naive['n_veh']} vehicles | {naive['total_km']:.1f} km | SLA {n_sla['sla_pct']}%")

    print("\n🤖 Running OR-Tools VRPTW (20s optimisation window)…")
    opt = solve_vrptw(dist, time_)

    if not opt:
        print("❌ No feasible solution. Check capacity/vehicle count.")
        sys.exit(1)

    o_sla = compute_sla(opt, time_, use_solver_times=True)
    print(f"   → {opt['n_veh']} vehicles | {opt['total_km']:.1f} km | SLA {o_sla['sla_pct']}%")

    print_report(naive, opt, n_sla, o_sla)

    # Save output for Layer 2 to consume
    output = {
        "dist":  dist,
        "time_": time_,
        "naive": {**naive, "sla": n_sla},
        "opt":   {**opt,
                  "sla": o_sla,
                  "routes": [{"vehicle": r["vehicle"],
                               "route_wt": r["route_wt"],
                               "dist_m": r["dist_m"],
                               "time_s": r["time_s"]}
                              for r in opt["routes"]]},
    }
    with open("layer1_output.json", "w") as f:
        json.dump(output, f, indent=2)
    print("\n💾  layer1_output.json saved — Layer 2 will consume this.")
