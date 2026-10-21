"""
QuantumFlow — Flask REST API  (G12)
api/app.py  ·  Owner: Frontend Engineer

Endpoints:
  POST /api/simulate   — run traffic simulation
  POST /api/optimize   — run classical or quantum optimizer
  GET  /api/compare    — side-by-side comparison of last two runs
  GET  /api/health     — liveness probe

The frontend must call these endpoints for ALL traffic data.
This module must NOT implement its own metric calculations.
"""

from __future__ import annotations

import os
import time
from functools import wraps
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from shared.validators import validate_traffic_input, validate_timing_plan
from simulator.traffic_env import TrafficGrid
from simulator.classical_solver import greedy_optimize
from metrics.evaluator import compare as evaluator_compare

# Lazy import of quantum module so the API still starts if Qiskit is missing
_quantum_available = True
try:
    from quantum.qaoa_runner import run_qaoa, mock_qaoa_result
except ImportError:
    _quantum_available = False

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DASH_DIR   = os.path.join(BASE_DIR, "..", "dashboard")

app = Flask(__name__, static_folder=None)
CORS(app)   # allow cross-origin requests from the dashboard

# In-memory result store (keyed by run_id) — suitable for single-session demo
_results: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _error(message: str, code: int = 400, field: Optional[str] = None):
    body = {"status": "error", "code": code, "message": message}
    if field:
        body["field"] = field
    return jsonify(body), code


def _ok(data: Dict) -> Any:
    data["status"] = "ok"
    return jsonify(data), 200


def _run_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000)}"


def _require_json(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not request.is_json:
            return _error("Request must have Content-Type: application/json")
        return fn(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Routes — Static dashboard
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(DASH_DIR, "index.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(os.path.join(DASH_DIR, "static"), filename)


# ---------------------------------------------------------------------------
# GET /api/health
# ---------------------------------------------------------------------------
@app.route("/api/health")
def health():
    return _ok({
        "quantum_available": _quantum_available,
        "version": "1.0.0",
    })


# ---------------------------------------------------------------------------
# POST /api/simulate
# ---------------------------------------------------------------------------
@app.route("/api/simulate", methods=["POST"])
@_require_json
def simulate():
    """
    Request body:
        { "grid_size": int, "num_vehicles": int,
          "time_steps": int (opt), "seed": int (opt) }

    Response 200:
        { "status": "ok", "grid_size", "grid",
          "vehicle_positions", "traffic_input", "run_id" }
    """
    data = request.get_json()

    # -- Validate required fields
    grid_size    = data.get("grid_size")
    num_vehicles = data.get("num_vehicles")
    if grid_size is None:
        return _error("Missing required field 'grid_size'.", field="grid_size")
    if num_vehicles is None:
        return _error("Missing required field 'num_vehicles'.", field="num_vehicles")

    try:
        grid_size    = int(grid_size)
        num_vehicles = int(num_vehicles)
    except (TypeError, ValueError):
        return _error("grid_size and num_vehicles must be integers.")

    if not (2 <= grid_size <= 10):
        return _error("grid_size must be between 2 and 10.", field="grid_size")
    if not (1 <= num_vehicles <= 200):
        return _error("num_vehicles must be between 1 and 200.", field="num_vehicles")

    time_steps = int(data.get("time_steps", 10))
    seed       = int(data.get("seed", 42))

    if not (1 <= time_steps <= 100):
        return _error("time_steps must be between 1 and 100.", field="time_steps")

    # -- Run simulation
    try:
        grid_obj = TrafficGrid(grid_size=grid_size, seed=seed)
        snapshot = grid_obj.run(num_vehicles=num_vehicles, time_steps=time_steps)
    except ValueError as exc:
        return _error(str(exc))

    run_id = _run_id("sim")
    _results[run_id] = {"type": "simulate", "snapshot": snapshot}

    return _ok({
        "run_id":            run_id,
        "grid_size":         snapshot["grid_size"],
        "grid":              snapshot["grid"],
        "vehicle_positions": snapshot["vehicle_positions"],
        "traffic_input":     snapshot["traffic_input"],
    })


# ---------------------------------------------------------------------------
# POST /api/optimize
# ---------------------------------------------------------------------------
@app.route("/api/optimize", methods=["POST"])
@_require_json
def optimize():
    """
    Request body:
        {
            "traffic_input": TrafficInput,
            "method":        "classical" | "quantum" | "mock",
            "p_layers":      int (opt, quantum only),
            "shots":         int (opt, quantum only)
        }

    Response 200:
        SolverResult fields + "run_id"
    """
    data         = request.get_json()
    traffic_input = data.get("traffic_input")
    method        = data.get("method", "classical")

    if traffic_input is None:
        return _error("Missing required field 'traffic_input'.", field="traffic_input")
    if method not in ("classical", "quantum", "mock"):
        return _error("method must be 'classical', 'quantum', or 'mock'.", field="method")

    # Validate traffic_input schema
    try:
        validate_traffic_input(traffic_input)
    except ValueError as exc:
        return _error(str(exc), field="traffic_input")

    # -- Dispatch to solver
    try:
        if method == "classical":
            result = greedy_optimize(traffic_input)

        elif method == "mock":
            if not _quantum_available:
                return _error(
                    "Qiskit not installed; mock mode unavailable.", code=503
                )
            result = mock_qaoa_result(traffic_input)

        else:  # quantum
            if not _quantum_available:
                return _error(
                    "Qiskit not installed. Install qiskit and qiskit-aer, "
                    "or use method='mock'.",
                    code=503,
                )
            p_layers = int(data.get("p_layers", 1))
            shots    = int(data.get("shots", 1024))

            if not (1 <= p_layers <= 5):
                return _error("p_layers must be between 1 and 5.", field="p_layers")
            if not (128 <= shots <= 8192):
                return _error("shots must be between 128 and 8192.", field="shots")

            result = run_qaoa(traffic_input, p_layers=p_layers, shots=shots)

    except ValueError as exc:
        return _error(str(exc))
    except Exception as exc:  # pylint: disable=broad-except
        return _error(f"Solver error: {exc}", code=500)

    run_id = _run_id(method)
    _results[run_id] = {"type": "optimize", "method": method, "result": result}

    return _ok({
        "run_id":        run_id,
        "algorithm":     result["algorithm"],
        "timing_plan":   result["timing_plan"],
        "cost":          result["cost"],
        "metrics":       result["metrics"],
        "runtime_ms":    result["runtime_ms"],
        "solver_status": result["status"],
        "error_msg":     result["error_msg"],
    })


# ---------------------------------------------------------------------------
# GET /api/compare?classical_id=<id>&quantum_id=<id>
# ---------------------------------------------------------------------------
@app.route("/api/compare")
def compare():
    """
    Compare two previously computed SolverResults.
    Pass run_ids returned from /api/optimize.
    """
    c_id = request.args.get("classical_id")
    q_id = request.args.get("quantum_id")

    if not c_id or not q_id:
        return _error(
            "Provide both 'classical_id' and 'quantum_id' query parameters."
        )

    c_entry = _results.get(c_id)
    q_entry = _results.get(q_id)

    if c_entry is None:
        return _error(f"Run ID '{c_id}' not found.", code=404)
    if q_entry is None:
        return _error(f"Run ID '{q_id}' not found.", code=404)

    if c_entry["type"] != "optimize":
        return _error(f"Run ID '{c_id}' is not an optimize result.")
    if q_entry["type"] != "optimize":
        return _error(f"Run ID '{q_id}' is not an optimize result.")

    comparison = evaluator_compare(c_entry["result"], q_entry["result"])
    return _ok(comparison)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port  = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    print(f"\n🚦 QuantumFlow API running on http://localhost:{port}")
    print(f"   Quantum solver available: {_quantum_available}")
    print(f"   Dashboard: http://localhost:{port}/\n")
    app.run(host="0.0.0.0", port=port, debug=debug)
