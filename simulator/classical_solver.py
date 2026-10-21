"""
QuantumFlow — Classical Greedy Signal Optimizer (Baseline)
Team Lead (Person A) · Phase 1, Hours 2-3
"""

from typing import Dict


def greedy_optimize(congestion_map: Dict[str, float]) -> Dict:
    """
    Classical greedy baseline: allocate green time proportional
    to congestion score.  Higher congestion → more green time.

    Args:
        congestion_map: dict mapping "(row,col)" → float in [0, 1]

    Returns:
        dict with keys: signal_timings, total_wait_time, metrics
    """
    if not congestion_map:
        raise ValueError("congestion_map must not be empty.")

    min_green = 10   # seconds
    max_green = 90   # seconds
    green_range = max_green - min_green

    signal_timings: Dict[str, int] = {}
    total_wait = 0.0

    for key, score in congestion_map.items():
        green_time = int(min_green + score * green_range)
        signal_timings[key] = green_time
        # Simplified wait model: congested intersections cause more wait
        total_wait += score * green_time * 0.5

    metrics = _compute_metrics(congestion_map, signal_timings)

    return {
        "method": "classical",
        "signal_timings": signal_timings,
        "total_wait_time": round(total_wait, 2),
        "quantum_energy": None,
        "iterations": 1,
        "runtime_ms": 0,
        "metrics": metrics,
    }


def _compute_metrics(
    congestion_map: Dict[str, float],
    signal_timings: Dict[str, int],
) -> Dict[str, float]:
    """Shared metric computation (also used by quantum solver)."""
    n = len(congestion_map)
    if n == 0:
        return {"throughput": 0.0, "avg_wait": 0.0, "congestion_score": 0.0}

    avg_congestion = sum(congestion_map.values()) / n
    avg_green = sum(signal_timings.values()) / n
    # Throughput heuristic: inversely proportional to congestion
    throughput = round(max(0.0, 1.0 - avg_congestion), 4)
    avg_wait = round(avg_congestion * 30, 2)   # crude model: 30s at full congestion
    congestion_score = round(avg_congestion, 4)

    return {
        "throughput": throughput,
        "avg_wait": avg_wait,
        "congestion_score": congestion_score,
    }
