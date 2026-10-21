"""
QuantumFlow — Shared Metrics Evaluator  (G5 resolved)
metrics/evaluator.py  ·  Owner: Team Lead

The ONLY place in the codebase where Metrics are calculated.
All solvers (classical, quantum, mock) must call evaluate() and
must NOT implement their own metric logic.

Changelog vs previous version:
  - evaluate() now accepts TrafficInput + TimingPlan (not Dict[str,float]).
  - Returns SolverResult (complete, typed).
  - compare() updated to work with SolverResult inputs.
"""

from __future__ import annotations

import math
from typing import Dict

from shared.types import TrafficInput, TimingPlan, Metrics, SolverResult
from shared.validators import (
    validate_traffic_input,
    validate_timing_plan,
    CYCLE_SEC,
    MIN_GREEN,
    MAX_GREEN,
)


# ---------------------------------------------------------------------------
# evaluate()
# ---------------------------------------------------------------------------
def evaluate(
    traffic_input: TrafficInput,
    timing_plan:   TimingPlan,
    algorithm:     str   = "unknown",
    runtime_ms:    float = 0.0,
    cost:          float | None = None,
) -> SolverResult:
    """
    Compute all Metrics and package into a SolverResult.

    Model:
        vehicles_served_i  = min(total_i, floor(total_i * green_fraction_i))
        green_fraction_i   = dominant_green / CYCLE_SEC
          where dominant_green = ns_green if ns_count >= ew_count else ew_green
        avg_wait_sec       = mean over intersections of
                             (1 - green_fraction_i) * CYCLE_SEC * congestion_i
        total_delay_sec    = sum of per-vehicle delays

    Args:
        traffic_input: TrafficInput — vehicle counts per approach.
        timing_plan:   TimingPlan  — must satisfy cycle + green-time constraints.
        algorithm:     Solver name for attribution.
        runtime_ms:    Wall-clock time of the calling solver (ms).
        cost:          QUBO/QAOA objective value; None for classical.

    Returns:
        SolverResult with status="ok" and error_msg=None.

    Raises:
        ValueError: if timing_plan violates constraints or keys mismatch.
    """
    validate_traffic_input(traffic_input)
    validate_timing_plan(timing_plan, traffic_input)

    total_vehicles   = 0
    vehicles_served  = 0
    total_delay      = 0.0
    wait_sum         = 0.0
    n = len(traffic_input)

    for iid, counts in traffic_input.items():
        ns_c = counts["ns_count"]
        ew_c = counts["ew_count"]
        total_i = ns_c + ew_c
        total_vehicles += total_i

        timing = timing_plan[iid]
        ns_g   = timing["ns_green"]
        ew_g   = timing["ew_green"]

        # Effective throughput: dominant approach gets its green, minority waits
        ns_served = _vehicles_served(ns_c, ns_g)
        ew_served = _vehicles_served(ew_c, ew_g)
        served_i  = ns_served + ew_served
        vehicles_served += served_i

        # Waiting vehicles
        waiting_i = total_i - served_i

        # Per-intersection average wait (seconds)
        # Waiting vehicles experience ~(red_time / 2) average wait
        ns_wait = (ew_g / 2) * (ns_c - ns_served) if ns_c > ns_served else 0.0
        ew_wait = (ns_g / 2) * (ew_c - ew_served) if ew_c > ew_served else 0.0
        total_delay += ns_wait + ew_wait
        wait_sum    += (ns_wait + ew_wait) / max(total_i, 1)

    remaining_queue = total_vehicles - vehicles_served
    avg_wait_sec    = (total_delay / total_vehicles) if total_vehicles > 0 else 0.0

    metrics: Metrics = {
        "total_vehicles":  total_vehicles,
        "vehicles_served": vehicles_served,
        "remaining_queue": remaining_queue,
        "avg_wait_sec":    round(avg_wait_sec, 2),
        "total_delay_sec": round(total_delay, 2),
        "runtime_ms":      round(runtime_ms, 1),
    }

    result: SolverResult = {
        "algorithm":   algorithm,
        "timing_plan": timing_plan,
        "cost":        round(cost, 4) if cost is not None else None,
        "metrics":     metrics,
        "runtime_ms":  round(runtime_ms, 1),
        "status":      "ok",
        "error_msg":   None,
    }
    return result


# ---------------------------------------------------------------------------
# compare()
# ---------------------------------------------------------------------------
def compare(classical: SolverResult, quantum: SolverResult) -> Dict:
    """
    Return a side-by-side comparison dict for the dashboard.

    Args:
        classical: SolverResult from greedy_optimize().
        quantum:   SolverResult from run_qaoa() or mock_qaoa_result().

    Returns:
        {
            "classical": Metrics,
            "quantum":   Metrics,
            "advantage": {
                "throughput_delta":    float,
                "wait_reduction_pct":  float,
                "cost_delta":          float | None,
            }
        }
    """
    cm = classical["metrics"]
    qm = quantum["metrics"]

    # Throughput delta: fraction of extra vehicles served by quantum
    tv = cm["total_vehicles"] or 1  # avoid div/0
    throughput_delta = round((qm["vehicles_served"] - cm["vehicles_served"]) / tv, 4)

    # Wait reduction %
    c_wait = cm["avg_wait_sec"] or 1e-9
    wait_reduction_pct = round((1 - qm["avg_wait_sec"] / c_wait) * 100, 2)

    # Cost delta (None if classical has no cost)
    cost_delta: float | None = None
    if quantum["cost"] is not None and classical["cost"] is not None:
        cost_delta = round(quantum["cost"] - classical["cost"], 4)

    return {
        "classical": dict(cm),
        "quantum":   dict(qm),
        "advantage": {
            "throughput_delta":   throughput_delta,
            "wait_reduction_pct": wait_reduction_pct,
            "cost_delta":         cost_delta,
        },
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _vehicles_served(queue: int, green_sec: int) -> int:
    """
    Estimate vehicles that clear in one green phase.
    Assumes a discharge rate of 1 vehicle per 2 seconds of green.
    """
    if queue == 0:
        return 0
    capacity = math.floor(green_sec / 2)   # vehicles / green phase
    return min(queue, capacity)
