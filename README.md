# QuantumFlow 🚦⚛️

**A 24-hour hackathon project** combining quantum computing (QAOA) with traffic signal optimisation.

## Quick Start

```bash
# 1. Clone
git clone https://github.com/Gagan-03C/VTUXIBM.git
cd VTUXIBM

# 2. Create virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure
copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux

# 5. Run the API server
python -m api.app

# 6. Open dashboard
start http://localhost:5000    # Windows
# open http://localhost:5000   # macOS
```

## Run Tests

```bash
pytest                       # all tests + coverage
pytest tests/test_validators.py -v   # validators only
pytest tests/test_solvers.py   -v   # classical solver + evaluator
pytest tests/test_qubo.py      -v   # QUBO builder
pytest tests/test_api.py       -v   # Flask API (no Qiskit needed)
```

## Project Structure

```
quantumflow/
├── docs/
│   └── INTERFACES.md          ← Authoritative API contracts (read this first)
├── shared/
│   ├── types.py               ← TrafficInput, TimingPlan, Metrics, SolverResult
│   └── validators.py          ← Cycle & green-time constraint enforcement
├── simulator/
│   ├── traffic_env.py         ← N×N grid simulation
│   ├── traffic_simulator.py   ← 4-intersection simulator (A, B, C, D)
│   ├── baseline.py            ← Fixed-time & traffic-responsive controllers
│   └── classical_solver.py    ← Greedy baseline
├── metrics/
│   ├── traffic_model.py       ← Single source of truth for signal evaluation
│   └── evaluator.py           ← Public facade for evaluate() & compare()
├── quantum/
│   ├── qubo_builder.py        ← QUBO matrix + decode → TimingPlan
│   └── qaoa_runner.py         ← Qiskit QAOA solver + mock
├── api/
│   └── app.py                 ← Flask REST API
├── dashboard/
│   ├── index.html             ← UI entry point
│   └── static/
│       ├── css/style.css
│       └── js/main.js
├── tests/
│   ├── test_validators.py
│   ├── test_traffic_env.py
│   ├── test_traffic_simulator.py
│   ├── test_baseline.py
│   ├── test_traffic_model.py
│   ├── test_solvers.py
│   ├── test_qubo.py
│   └── test_api.py
├── requirements.txt
├── pytest.ini
└── .env.example
```

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/simulate` | Run traffic simulation |
| `POST` | `/api/optimize` | Run classical or quantum solver |
| `GET` | `/api/compare` | Side-by-side comparison |
| `GET` | `/api/health` | Liveness probe |

See [`docs/INTERFACES.md`](docs/INTERFACES.md) for full request/response schemas.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PORT` | `5000` | API server port |
| `FLASK_DEBUG` | `1` | Enable Flask debug mode |
| `IBMQ_TOKEN` | *(blank)* | Real IBMQ backend token |
| `USE_REAL_BACKEND` | `0` | Set to `1` to use IBMQ |

## Traffic Model

- **Cycle:** 60 seconds fixed
- **Green limits:** 15–45 seconds per approach
- **QUBO levels:** 4 discrete ns_green choices `[15, 25, 35, 45]`
- **ew_green** is always derived as `60 − ns_green`

## Team

| Role | Files owned |
|---|---|
| Team Lead | `shared/`, `simulator/`, `metrics/`, `tests/` |
| Quantum Engineer | `quantum/`, `tests/test_qubo.py` |
| Frontend Engineer | `api/`, `dashboard/`, `tests/test_api.py` |
