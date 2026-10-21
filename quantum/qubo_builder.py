"""
QuantumFlow — QUBO Builder
Quantum Engineer (Person B) · Phase 1, Hours 1-2

Formulates the traffic signal timing problem as a
Quadratic Unconstrained Binary Optimization (QUBO) problem.
"""

import numpy as np
from typing import Dict, List, Tuple


# Discretize green times into NUM_LEVELS binary choices per intersection
NUM_LEVELS = 4          # 2 qubits per intersection
MIN_GREEN = 10          # seconds
MAX_GREEN = 90          # seconds


def _green_levels() -> List[int]:
    """Return the discrete green-time levels."""
    step = (MAX_GREEN - MIN_GREEN) // (NUM_LEVELS - 1)
    return [MIN_GREEN + i * step for i in range(NUM_LEVELS)]


def build_qubo(
    congestion_map: Dict[str, float],
    penalty_lambda: float = 5.0,
) -> Tuple[np.ndarray, List[str], List[int]]:
    """
    Build QUBO matrix Q such that x^T Q x is minimised when signal
    timings balance congestion across the grid.

    Variables: for each intersection i and level k → binary var x_{i,k}
    Total variables: n_intersections × NUM_LEVELS

    Args:
        congestion_map: dict "(row,col)" → float [0,1]
        penalty_lambda: weight for the one-hot constraint term

    Returns:
        Q:          (N×N) numpy QUBO matrix (upper-triangular convention)
        var_labels: list of variable labels  e.g. "(0,0)_lvl0"
        keys:       ordered list of intersection keys
    """
    keys = sorted(congestion_map.keys())
    n_intersections = len(keys)
    n_vars = n_intersections * NUM_LEVELS
    levels = _green_levels()

    Q = np.zeros((n_vars, n_vars))

    def var_idx(i: int, k: int) -> int:
        return i * NUM_LEVELS + k

    for i, key in enumerate(keys):
        score = congestion_map[key]

        # Objective: prefer high green time for congested intersections
        for k, green in enumerate(levels):
            idx = var_idx(i, k)
            # Higher congestion → reward high green (negative = lower energy)
            Q[idx, idx] -= score * green / MAX_GREEN

        # One-hot constraint: exactly one level selected per intersection
        for k1 in range(NUM_LEVELS):
            for k2 in range(NUM_LEVELS):
                if k1 != k2:
                    Q[var_idx(i, k1), var_idx(i, k2)] += penalty_lambda
            Q[var_idx(i, k1), var_idx(i, k1)] -= penalty_lambda  # linear term

        # Conflict penalty: adjacent high-congestion pairs shouldn't all get max green
        row_i, col_i = _parse_key(key)
        for j, other_key in enumerate(keys):
            if j <= i:
                continue
            row_j, col_j = _parse_key(other_key)
            # Only penalise direct neighbours
            if abs(row_i - row_j) + abs(col_i - col_j) == 1:
                conflict_score = score * congestion_map[other_key]
                for k in range(NUM_LEVELS):
                    Q[var_idx(i, k), var_idx(j, k)] += conflict_score * 2.0

    # Symmetrise (QUBO convention: upper-triangular, but symmetrised for solvers)
    Q = (Q + Q.T) / 2

    var_labels = [f"{key}_lvl{k}" for key in keys for k in range(NUM_LEVELS)]
    return Q, var_labels, keys


def decode_solution(
    bitstring: str,
    keys: List[str],
) -> Dict[str, int]:
    """
    Decode a QUBO bitstring into signal timings.

    Args:
        bitstring: binary string of length n_intersections × NUM_LEVELS
        keys:      ordered intersection keys (same order used in build_qubo)

    Returns:
        signal_timings: dict "(row,col)" → int green seconds
    """
    if len(bitstring) != len(keys) * NUM_LEVELS:
        raise ValueError(
            f"Bitstring length {len(bitstring)} != {len(keys) * NUM_LEVELS}"
        )
    levels = _green_levels()
    timings = {}

    for i, key in enumerate(keys):
        segment = bitstring[i * NUM_LEVELS: (i + 1) * NUM_LEVELS]
        # Find the active level; if none or multiple, pick the highest set bit
        selected = MAX_GREEN  # fallback to max if no bit set
        for k, bit in enumerate(segment):
            if bit == "1":
                selected = levels[k]
                break
        timings[key] = selected

    return timings


def _parse_key(key: str) -> Tuple[int, int]:
    """Parse "(row,col)" → (int, int)."""
    stripped = key.strip("()")
    parts = stripped.split(",")
    return int(parts[0]), int(parts[1])
