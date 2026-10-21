"""
QuantumFlow — Shared Metrics Evaluator
Team Lead (Person A) · Phase 1, Hours 3-4
Both TL and QE import from this module — do not change signatures without team sync.
"""

from typing import Dict


def evaluate(
    congestion_map: Dict[str, float],
    signal_timings: Dict[str, int],
    method: str = "unknown",
    runtime_ms: float = 0.0,
) -> Dict:
    """
    Evaluate a signal-timing solution against the congestion map.

    Args:
        congestion_map: dict "(row,col)" → float [0,1]
        signal_timings: dict "(row,col)" → int green seconds
        method:         "classical" | "quantum" | "unknown"
        runtime_ms:     wall-clock solver time in milliseconds

    Returns:
        Standardised metrics dict matching the API contract in §4.2.
    """
    if not congestion_map:
        raise ValueError("congestion_map must not be empty.")
    if set(signal_timings.keys()) != set(congestion_map.keys()):
        raise ValueError("signal_timings keys must match congestion_map keys.")

    n = len(congestion_map)
    scores = list(congestion_map.values())
    greens = list(signal_timings.values())

    avg_congestion = sum(scores) / n
    avg_green = sum(greens) / n

    # Wait time model: congested roads with short green → high wait
    total_wait = sum(
        congestion_map[k] * max(0, 90 - signal_timings[k]) * 0.3
        for k in congestion_map
    )
    avg_wait = total_wait / n if n else 0.0

    # Throughput: fraction of intersections with congestion < 0.5
    throughput = sum(1 for s in scores if s < 0.5) / n

    # Congestion score: weighted average (high-congestion nodes weighted more)
    congestion_score = sum(s ** 2 for s in scores) / n

    return {
        "method": method,
        "runtime_ms": round(runtime_ms, 1),
        "total_wait_time": round(total_wait, 2),
        "metrics": {
            "throughput": round(throughput, 4),
            "avg_wait": round(avg_wait, 2),
            "congestion_score": round(congestion_score, 4),
        },
    }


def compare(classical_result: Dict, quantum_result: Dict) -> Dict:
    """
    Return a side-by-side comparison dict for the dashboard.
    Both inputs must be results from evaluate().
    """
    def _get(d, *keys):
        for k in keys:
            d = d.get(k, {})
        return d

    return {
        "classical": {
            "throughput": _get(classical_result, "metrics", "throughput"),
            "avg_wait": _get(classical_result, "metrics", "avg_wait"),
            "congestion_score": _get(classical_result, "metrics", "congestion_score"),
            "total_wait_time": classical_result.get("total_wait_time"),
            "runtime_ms": classical_result.get("runtime_ms"),
        },
        "quantum": {
            "throughput": _get(quantum_result, "metrics", "throughput"),
            "avg_wait": _get(quantum_result, "metrics", "avg_wait"),
            "congestion_score": _get(quantum_result, "metrics", "congestion_score"),
            "total_wait_time": quantum_result.get("total_wait_time"),
            "runtime_ms": quantum_result.get("runtime_ms"),
        },
        "advantage": {
            "throughput_delta": round(
                _get(quantum_result, "metrics", "throughput") -
                _get(classical_result, "metrics", "throughput"), 4
            ),
            "wait_reduction_pct": round(
                (1 - _get(quantum_result, "metrics", "avg_wait") /
                 max(_get(classical_result, "metrics", "avg_wait"), 1e-9)) * 100, 2
            ),
        },
    }
