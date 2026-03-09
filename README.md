# 🚚 AI Route Optimization Engine

> **AI-powered last-mile logistics platform** combining route optimization, real-time traffic intelligence, continuous ETA learning, and forward + reverse logistics — built for Bengaluru's urban delivery network.

---

## 📺 Live Demo

```bash
streamlit run app.py
# Open: http://localhost:8501
```

---

## 🏗️ Project Architecture

```
route optimization/
│
├── app.py                    ← Streamlit dashboard (single-file frontend)
├── generate_ppt.py           ← Auto-generates pitch deck from real results
├── requirements.txt
│
├── layer1/                   ← Route Optimization (VRPTW)
│   ├── data/
│   │   └── network.py        ← 15-node Bengaluru network (coordinates, orders, vehicles)
│   └── src/
│       ├── matrices.py       ← OSRM real-road distance/time matrix builder
│       ├── naive_solver.py   ← Greedy nearest-neighbour baseline
│       ├── optimizer.py      ← OR-Tools VRPTW solver
│       └── metrics.py        ← SLA + cost analysis
│
├── layer2/                   ← Traffic Intelligence & Rerouting
│   ├── data/
│   │   └── distance_matrix.json   ← Cached OSRM matrix
│   ├── src/
│   │   ├── traffic_engine.py      ← 3 Bengaluru traffic events + matrix modifier
│   │   ├── rerouter.py            ← simulate_route(), congestion detector
│   │   └── scenario_runner.py     ← A/B/C scenario orchestrator
│   └── run_layer2.py              ← Standalone validation script
│
├── layer3/                   ← Continuous Learning (EMA)
│   ├── data/
│   │   └── eta_corrections.json   ← Learned per-segment delay factors
│   ├── src/
│   │   ├── eta_learner.py         ← EMA correction table (per-segment, per-time-band)
│   │   └── delivery_sim.py        ← Simulates actual delivery with hidden delays
│   └── run_layer3.py              ← 4-round learning loop entry point
│
└── module2/                  ← Forward + Reverse Logistics
    ├── data/
    │   ├── network_m2.py          ← 18-node network (14 delivery + 3 pickup stops)
    │   └── distance_matrix_m2.json
    ├── src/
    │   ├── matrices_m2.py         ← 18×18 OSRM matrix builder
    │   ├── naive_solver_m2.py     ← Siloed fleet baseline (1 vehicle per order)
    │   ├── optimizer_m2.py        ← Unified VRPTW (deliveries + pickups mixed)
    │   └── metrics_m2.py          ← SLA split by delivery vs pickup type
    └── run_module2.py             ← Standalone validation script
```

---

## ⚡ Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

**`requirements.txt`**
```
ortools>=9.8.3296
streamlit
folium
streamlit-folium
plotly
pandas
python-pptx
```

### 2. Run the Dashboard

```bash
streamlit run app.py
```

The app auto-runs Layer 1 on first load. Use the sidebar buttons to trigger Layer 2, Layer 3, and Module 2.

### 3. Validate Each Layer Standalone

```bash
python layer2/run_layer2.py    # Traffic + rerouting scenarios
python layer3/run_layer3.py    # ETA learning over 4 rounds
python module2/run_module2.py  # Forward + reverse logistics
```

### 4. Generate Pitch Deck

```bash
python generate_ppt.py
# Output: SmartDeliver_AI_v2.pptx (10 slides, dark theme, real numbers)
```

---

## 📦 Layer 1 — Route Optimization

**Goal:** Replace 1-vehicle-per-order dispatch with optimally batched multi-stop routes.

### How It Works

| Step | Component | Description |
|------|-----------|-------------|
| 1 | `matrices.py` | Fetches real travel times from OSRM (OpenStreetMap routing), caches as JSON |
| 2 | `naive_solver.py` | Greedy nearest-neighbour: each vehicle visits one stop and returns (baseline) |
| 3 | `optimizer.py` | Google OR-Tools VRPTW: minimizes total distance with soft time-window constraints and priority penalties |
| 4 | `metrics.py` | Computes SLA compliance (on-time %), cost (₹/km), HIGH-priority breach counts |

### Network

- **Depot:** Koramangala Hub (12.9352°N, 77.6245°E)
- **14 delivery stops** across Bengaluru (Jayanagar, HSR Layout, Electronic City, Indiranagar, Whitefield)
- **4 vehicles**, capacity 5 units each
- **Time windows:** 35-minute to 4-hour windows depending on priority

### Results

| Metric | Naive (No AI) | AI Optimized | Improvement |
|--------|--------------|--------------|-------------|
| Vehicles | 14 | 4 | −71% |
| Distance | 256 km | 122 km | −52% |
| SLA Compliance | 35.7% | 100% | +64.3 pts |
| Cost | ₹3,072 | ₹1,465 | ₹1,607 saved |

### Files

- **`layer1/data/network.py`** — All coordinates, order specs (demand, TW, priority), vehicle definitions
- **`layer1/src/optimizer.py`** — OR-Tools setup: distance arc cost, time dimension with soft upper bounds, capacity dimension, GLS metaheuristic, 25s solve limit

---

## 🚦 Layer 2 — Real-Time Traffic Intelligence

**Goal:** Simulate real Bengaluru congestion events and prove AI rerouting outperforms naive routing.

### Three Scenarios

| Scenario | Description | Story |
|----------|-------------|-------|
| **A — Naive** | Greedy routing, no AI | 14 vehicles, 35.7% SLA — what happens without AI |
| **B — AI + Clear Roads** | OR-Tools VRPTW on normal times | 4 vehicles, 100% SLA — AI's baseline value |
| **C — AI + Traffic** | OR-Tools re-solved on congested time matrix | 4 vehicles, 93%+ SLA — AI adapts in real-time |

### Traffic Events

| Event ID | Location | Severity | Multiplier |
|----------|----------|----------|------------|
| EVT_001 | Hosur Rd / Silk Board | SEVERE | 2.8× |
| EVT_002 | Sarjapur–Bellandur ORR | HIGH | 2.0× |
| EVT_003 | Citywide rain congestion | MODERATE | 1.5× |

### Map Visualizations

- **Scenario A:** 14 multi-coloured chaotic routes, red 🚨 badges on missed stops
- **Scenario B:** 4 clean routes, all ✅ green badges
- **Scenario C:** 
  - 🚧 road-block markers at congested junctions
  - 👻 gray dashed ghost lines = original B route (what would have been taken)
  - ⟹ Thick animated blue AntPath = AI rerouted path avoiding congestion

### Key Files

- **`traffic_engine.py`** — `TRAFFIC_EVENTS` dict, `apply_combined_events()` multiplies affected matrix cells
- **`rerouter.py`** — `simulate_route()` walks each route stop-by-stop tracking arrival time vs time window
- **`scenario_runner.py`** — Runs naive solver (Scenario A), VRPTW on clear times (B), VRPTW on congested times (C), returns unified comparison dict

---

## 🧠 Layer 3 — Continuous ETA Learning

**Goal:** Close the gap between OSRM predicted travel times and real Bengaluru travel times through Exponential Moving Average (EMA) correction.

### How EMA Works

```
new_factor = (1 - α) × old_factor + α × observed_factor
```

Where `α = 0.3` — 30% weight on new observation, 70% on historical average.

**Example — Hosur Road:**
- OSRM predicted: 800s
- Round 1 actual: 1,240s → observed factor = 1.55
- After Round 1: `factor = 0.7 × 1.0 + 0.3 × 1.55 = 1.165`
- After 4 rounds: factor converges to ~1.47 (realistic for peak hours)

### Time Bands

| Band | Time | Purpose |
|------|------|---------|
| EARLY | 0–60 min | Light traffic corrections |
| MID | 60–120 min | Morning rush |
| LATE | 120+ min | Peak / afternoon congestion |

### Results (4-Round Loop)

| Round | ETA Error Before | ETA Error After | Corrections Learned |
|-------|-----------------|-----------------|---------------------|
| 1 | ~22% | ~15% | Growing |
| 2 | ~15% | ~10% | Growing |
| 3 | ~10% | ~7% | Stable |
| 4 | ~7% | ~5% | Converged |

**Total: ~22% → 5% ETA error reduction over 4 delivery days.**

### Key Files

- **`eta_learner.py`** — `ETALearner` class: stores `factors[seg_key][band]`, `record_observations()`, `apply_to_matrix()`, `compute_mae()`, `save()/load()`
- **`delivery_sim.py`** — `simulate_actual_times()`: applies hidden systematic delay + Gaussian noise to simulate real-world vs predicted travel

---

## 🔄 Module 2 — Forward + Reverse Logistics

**Goal:** Prove that one unified AI fleet can handle both outbound deliveries and customer return pickups simultaneously, eliminating the separate "siloed" fleets used by traditional logistics.

### The Core Insight

> A delivery vehicle that drops a package at a customer's door has **freed capacity**. AI uses that freed space to collect a return from a nearby customer on the same loop — zero extra trips, zero deadhead miles.

### Network (18 nodes)

- **1 depot** — Koramangala Hub
- **14 delivery stops** — outbound packages across Bengaluru zones A/B/C/D
- **3 return pickup stops** — co-located near delivery zones (Koramangala, HSR Layout, Agara Lake)
- **4 vehicles**, capacity 7 units each

### Comparison

| Metric | Siloed Fleets (No AI) | Unified AI Fleet | Improvement |
|--------|-----------------------|-----------------|-------------|
| Total vehicles | 17 (14 delivery + 3 pickup) | 4 | −76% |
| Total distance | 281 km | 120 km | −57% |
| SLA (overall) | 29.4% | 94.1% | +64.7 pts |
| Pickup SLA | — (separate) | 100% | Perfect |
| Cost | ₹3,372 | ₹1,440 | ₹1,932 saved |

### Map

- 🟢 **Green circle** = delivery stop
- 🔴 **Red circle** = return pickup stop
- Numbers = stop sequence order per vehicle

### Key Files

- **`network_m2.py`** — `ALL_LOCS_M2` (18 nodes with stop_type field), `ORDERS_M2` (14 delivery + 3 pickup orders)
- **`optimizer_m2.py`** — Standard OR-Tools VRPTW with capacity constraint treating both delivery and pickup demand identically
- **`metrics_m2.py`** — `compute_sla_m2()` splits SLA reporting by stop type (DELIVERY vs PICKUP)

---

## 🖥️ Dashboard (`app.py`)

Single Streamlit file — 1,300+ lines — covering all layers in one interface.

### Structure

```
Sidebar
├── 🚀 Run Optimization        ← Triggers Layer 1 (auto-runs on first load)
├── 🔄 Clear Cache & Re-solve
│
└── Key Features
    ├── 🚦 Traffic & Rerouting  ← Checkboxes (Hosur / ORR / Rain) + ▶ Simulate
    ├── 🧠 ETA Learning         ← ▶ Run Learning
    └── 🔄 Forward & Reverse    ← ▶ Run Module 2

Main Area
├── Tab 1: 🗺️ Side-by-Side Maps    (Naive vs AI route maps, click stops for details)
├── Tab 2: 📈 Performance Charts   (distance, time, SLA, cost bar charts)
└── Tab 3: 📋 Route Details        (per-stop table with SLA status + delays)

Inline Sections (appear after sidebar button click)
├── 🚦 Layer 2: 3-Scenario KPIs + 3 map tabs (A/B/C) + congested segments table
├── 🧠 Layer 3: ETA error chart + correction factor table + round-by-round data
└── 🔄 Module 2: KPI metrics + unified fleet map + comparison charts
```

### Key Dependencies

| Package | Use |
|---------|-----|
| `streamlit` | Web framework |
| `folium` | Interactive Leaflet maps |
| `streamlit-folium` | Embeds Folium maps in Streamlit |
| `folium.plugins.AntPath` | Animated route lines (Layer 2 Scenario C) |
| `plotly` | Bar and line charts |
| `pandas` | Data tables |
| `ortools` | VRPTW optimization engine |

---

## 📊 Output Files

| File | Contents |
|------|----------|
| `layer1_output.json` | `naive` + `opt` route details, distance matrix, SLA |
| `layer2_output.json` | Congested segments per event combo |
| `layer3_output.json` | Round-by-round EMA results, learned correction factors |
| `module2_output.json` | Naive vs unified fleet routes, SLA split by stop type |
| `layer3/data/eta_corrections.json` | Persisted EMA correction table |

---

## 🛠️ Technology Stack

| Component | Technology |
|-----------|-----------|
| Optimization | Google OR-Tools (VRPTW, GLS metaheuristic, 25s limit) |
| Road data | OSRM (`router.project-osrm.org`) — real Bengaluru distances |
| Fallback | Haversine × 1.35 road-factor if OSRM unavailable |
| Dashboard | Streamlit |
| Maps | Folium + AntPath plugin |
| Charts | Plotly |
| ML | Custom EMA correction (no external ML library) |
| Deck | python-pptx (`generate_ppt.py`) |

---

## 🔬 Design Decisions

### Why OR-Tools VRPTW?
- Industry-standard (used by Google, UPS, FedEx planning systems)
- Handles time windows, vehicle capacity, and priority penalties natively
- 25-second solve time is acceptable for daily batch planning

### Why EMA (not ML)?
- No training data required — works from day 1
- Interpretable: each factor is a human-readable multiplier
- Incremental: updates after every delivery round automatically

### Why simulate traffic (not live API)?
- Bengaluru real-time traffic APIs (HERE, TomTom) require paid keys
- Simulated 2.5–2.8× multipliers on Hosur Rd / Silk Board are realistic
- Judges can reproduce and verify the demo deterministically

### Single-file dashboard (`app.py`)?
- All state lives in `st.session_state` — zero backend server needed
- Easier to demo: one command, localhost, no Docker/deploy

---

## 📁 Running Individual Layers

```bash
# Layer 1 — build matrix + solve + print report
python layer1/run_layer1.py

# Layer 2 — 5 traffic event combinations, A/B/C comparison
python layer2/run_layer2.py

# Layer 3 — 4-round EMA learning loop
python layer3/run_layer3.py

# Module 2 — forward + reverse logistics comparison
python module2/run_module2.py

# Generate pitch deck (requires layer1/3/module2 JSON outputs)
python generate_ppt.py
```

---

## 📈 Cumulative Business Impact

| Source | Saving |
|--------|--------|
| Layer 1 — fleet consolidation | 10 fewer vehicles, ₹1,607/cycle |
| Layer 2 — avoided SLA breaches | 93%+ vs 35.7% under congestion |
| Layer 3 — ETA accuracy | 22% → 5% prediction error |
| Module 2 — unified fleet | 13 fewer vehicles, ₹1,932/cycle |
| **Total per cycle** | **₹3,539 saved, 23 vehicles eliminated** |
| **At scale (1,000 deliveries/day)** | **₹14.6L/month in fuel + ₹8L in fleet costs** |

---

## 👤 Author

Built for competitive presentation — --rebase
Stack: Python · OR-Tools · Streamlit · Folium · OSRM
