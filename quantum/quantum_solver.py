"""
QuantumFlow — Genuine QAOA Quantum Solver
quantum/quantum_solver.py  ·  Owner: Quantum Engineer

Executes genuine Quantum Approximate Optimization Algorithm (QAOA) on local
quantum simulator (Qiskit Aer) using installed, compatible Qiskit APIs.

-----------------------------------------------------------------------------
OVERVIEW & REPRODUCIBILITY GUARANTEE
-----------------------------------------------------------------------------
This solver converts QuantumFlow's validated 4-variable binary traffic objective
(or any QuadraticProgram) into an Ising Hamiltonian and executes genuine QAOA.

NO FAKE/MOCK RESULTS:
The measured bitstring, objective value, and probability distribution come
directly from the quantum circuit execution on Qiskit Aer's Sampler primitive.
Exhaustive search is NEVER substituted for QAOA results.

REPRODUCIBLE SETTINGS:
- Circuit depth (p_layers): 1 or 2 (default 1)
- Classical optimizer: COBYLA with bounded iterations (default maxiter=50)
- Quantum simulator: Qiskit Aer Sampler primitive
- Shot count: 1024 (default)
- Random seed: 42 (default for determinism in sampling and circuit simulation)
-----------------------------------------------------------------------------
"""

from __future__ import annotations

import sys
import time
import warnings
from typing import Any, Dict, List, Optional, Sequence, Tuple
from typing_extensions import TypedDict

import numpy as np

# Compatible Qiskit and Qiskit-Optimization imports
from qiskit_aer.primitives import Sampler as AerSampler
from qiskit_algorithms import QAOA
from qiskit_algorithms.optimizers import COBYLA, SPSA
from qiskit_optimization import QuadraticProgram
from qiskit_optimization.algorithms import MinimumEigenOptimizer

from quantum.binary_qubo import (
    DEFAULT_INTERSECTIONS,
    GRID_INTERSECTIONS,
    NUM_VARIABLES,
    build_binary_qubo,
    compute_intended_cost,
    evaluate_qubo_energy,
)
from quantum.reference_enumerator import decode_bitstring
from metrics.traffic_model import evaluate as evaluate_traffic
from shared.types import SolverResult, TimingPlan, TrafficInput
from shared.validators import validate_timing_plan, validate_traffic_input


# ---------------------------------------------------------------------------
# Result Data Structures
# ---------------------------------------------------------------------------
class QAOAMeasurementSample(TypedDict):
    """A single state measured during QAOA circuit execution."""
    bitstring: str
    fval: float
    probability: float
    status: str


class QuantumSolverResult(TypedDict):
    """Complete result returned by the genuine QAOA quantum solver."""
    bitstring: str
    objective_value: float
    status: str
    runtime_ms: float
    timing_plan: TimingPlan
    solver_result: SolverResult
    samples: List[QAOAMeasurementSample]
    optimal_parameters: Optional[Dict[str, float]]
    variable_names: List[str]
    error_msg: Optional[str]
    shots: int
    p_layers: int
    maxiter: int
    seed: Optional[int]


# ---------------------------------------------------------------------------
# QuadraticProgram Conversion
# ---------------------------------------------------------------------------
def qubo_to_quadratic_program(
    Q: np.ndarray,
    offset: float,
    var_names: Sequence[str],
    problem_name: str = "quantumflow_qubo",
) -> QuadraticProgram:
    """
    Convert a QUBO matrix Q and constant offset into a Qiskit QuadraticProgram.

    Handles both upper-triangular and symmetric QUBO matrices identically:
        quadratic coefficient for (x_i, x_j) with i < j is Q[i, j] + Q[j, i].

    Args:
        Q: 2D numpy array of shape (N, N).
        offset: Scalar constant offset.
        var_names: Ordered variable names corresponding to indices 0..N-1.
        problem_name: Name label for the QuadraticProgram.

    Returns:
        QuadraticProgram ready for Qiskit optimization algorithms.
    """
    n = len(var_names)
    if Q.shape != (n, n):
        raise ValueError(f"Matrix shape {Q.shape} does not match {n} variable names")

    qp = QuadraticProgram(problem_name)
    for name in var_names:
        qp.binary_var(name)

    # Linear terms: diagonal entries Q[i, i]
    linear: Dict[str, float] = {var_names[i]: float(Q[i, i]) for i in range(n)}

    # Pairwise quadratic terms: off-diagonal entries
    quadratic: Dict[Tuple[str, str], float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            coeff = float(Q[i, j] + Q[j, i])
            if abs(coeff) > 1e-12:
                quadratic[(var_names[i], var_names[j])] = coeff

    qp.minimize(constant=float(offset), linear=linear, quadratic=quadratic)
    return qp


# ---------------------------------------------------------------------------
# Core QAOA Execution Engine
# ---------------------------------------------------------------------------
def execute_qaoa(
    qp: QuadraticProgram,
    p_layers: int = 1,
    shots: int = 1024,
    maxiter: int = 50,
    seed: Optional[int] = 42,
    initial_point: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    """
    Execute genuine QAOA on a QuadraticProgram using local AerSampler and COBYLA.

    Args:
        qp: Qiskit QuadraticProgram to solve.
        p_layers: QAOA circuit depth (reps).
        shots: Number of measurement shots on AerSimulator.
        maxiter: Maximum classical parameter optimizer iterations.
        seed: Random seed for reproducible quantum simulation.
        initial_point: Optional initial variational parameters (length 2 * p_layers).

    Returns:
        Dict with execution results: best_x, bitstring, fval, samples, runtime_ms,
        optimal_parameters, and raw Qiskit result.
    """
    t0 = time.perf_counter()

    # 1. Local Quantum Simulator Primitive (AerSampler)
    sampler = AerSampler()
    if seed is not None:
        sampler.set_options(shots=shots, seed_simulator=seed)
    else:
        sampler.set_options(shots=shots)

    # 2. Classical Parameter Optimizer
    optimizer = COBYLA(maxiter=maxiter)

    # 3. Deterministic initial point for reproducible convergence
    if initial_point is not None:
        init_pt = list(initial_point)
    elif seed is not None:
        rng = np.random.default_rng(seed)
        init_pt = rng.uniform(0.0, np.pi, size=2 * p_layers).tolist()
    else:
        init_pt = None

    # 4. QAOA Ansatz & MinimumEigenOptimizer
    qaoa = QAOA(
        sampler=sampler,
        optimizer=optimizer,
        reps=p_layers,
        initial_point=init_pt,
    )
    meo = MinimumEigenOptimizer(qaoa)

    # 4. Execute QAOA circuit optimization
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw_result = meo.solve(qp)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # 5. Extract measured variable vector and bitstring
    # Variable ordering in qp.variables is strictly preserved:
    var_names = [v.name for v in qp.variables]
    best_x = [int(round(val)) for val in raw_result.x]
    bitstring = "".join(str(val) for val in best_x)
    fval = float(raw_result.fval)

    # 6. Extract measurement distribution
    samples: List[QAOAMeasurementSample] = []
    if hasattr(raw_result, "samples") and raw_result.samples:
        for s in raw_result.samples:
            s_bits = "".join(str(int(round(v))) for v in s.x)
            samples.append({
                "bitstring": s_bits,
                "fval": float(s.fval),
                "probability": float(s.probability),
                "status": str(s.status),
            })
        # Sort samples by probability descending, breaking ties by fval then bitstring
        samples.sort(key=lambda s: (-round(s["probability"], 5), s["fval"], s["bitstring"]))


    # 7. Extract optimal variational parameters (beta, gamma) if available
    optimal_params: Optional[Dict[str, float]] = None
    if hasattr(raw_result, "min_eigen_solver_result") and raw_result.min_eigen_solver_result:
        eigen_res = raw_result.min_eigen_solver_result
        if hasattr(eigen_res, "optimal_point") and eigen_res.optimal_point is not None:
            pt = eigen_res.optimal_point
            optimal_params = {f"theta_{k}": float(val) for k, val in enumerate(pt)}

    return {
        "best_x": best_x,
        "bitstring": bitstring,
        "fval": fval,
        "samples": samples,
        "runtime_ms": elapsed_ms,
        "optimal_parameters": optimal_params,
        "raw_result": raw_result,
        "var_names": var_names,
    }


# ---------------------------------------------------------------------------
# 1. Known Small Optimization Example
# ---------------------------------------------------------------------------
def run_small_example(
    p_layers: int = 1,
    shots: int = 1024,
    maxiter: int = 50,
    seed: Optional[int] = 42,
) -> Dict[str, Any]:
    """
    Run genuine QAOA on an analytically known small 2-variable optimization problem.

    Objective:
        minimize f(x_0, x_1) = -x_0 - x_1 + 2 * x_0 * x_1
    Truth table:
        x=(0,0) -> f = 0
        x=(0,1) -> f = -1  (Ground state)
        x=(1,0) -> f = -1  (Ground state)
        x=(1,1) -> f = 0
    Ground state value: -1.0, achieved by x=[0,1] or x=[1,0].
    """
    qp = QuadraticProgram("known_small_example")
    qp.binary_var("x0")
    qp.binary_var("x1")
    qp.minimize(linear={"x0": -1.0, "x1": -1.0}, quadratic={("x0", "x1"): 2.0})

    res = execute_qaoa(
        qp=qp,
        p_layers=p_layers,
        shots=shots,
        maxiter=maxiter,
        seed=seed,
    )

    # Verify convergence to known minimum
    is_optimal = res["fval"] == -1.0 and res["best_x"] in ([0, 1], [1, 0])
    res["is_optimal"] = is_optimal
    return res


# ---------------------------------------------------------------------------
# 2. QuantumFlow Traffic QUBO Solver
# ---------------------------------------------------------------------------
def solve_traffic_qubo(
    traffic_input: TrafficInput,
    coord_weight: float = 0.0,
    p_layers: int = 1,
    shots: int = 1024,
    maxiter: int = 50,
    seed: Optional[int] = 42,
    intersections: Optional[Sequence[str]] = None,
) -> QuantumSolverResult:
    """
    Solve QuantumFlow's 4-intersection signal timing optimization using genuine QAOA.

    Steps:
        1. Validate traffic input snapshot.
        2. Build exact QUBO matrix Q and offset c for the 4 binary choices.
        3. Convert to Qiskit QuadraticProgram preserving variable ordering:
           x_0 = A (0,0), x_1 = B (0,1), x_2 = C (1,0), x_3 = D (1,1).
        4. Execute genuine QAOA on Qiskit Aer local quantum simulator.
        5. Extract best measured bitstring, objective value, and runtime.
        6. Decode bitstring to TimingPlan and evaluate with shared traffic evaluator.

    Args:
        traffic_input: Queue counts for all 4 intersections.
        coord_weight: Weight for grid edge coordination penalties (default 0.0).
        p_layers: QAOA circuit depth (default 1).
        shots: Measurement shots on AerSimulator (default 1024).
        maxiter: Maximum COBYLA optimizer iterations (default 50).
        seed: Random seed for reproducible quantum execution (default 42).
        intersections: Ordered 4-intersection list (defaults to traffic_input keys).

    Returns:
        QuantumSolverResult dict with bitstring, objective_value, status, runtime_ms,
        timing_plan, solver_result, and measurement samples.
    """
    validate_traffic_input(traffic_input)

    inter_list = list(intersections) if intersections is not None else (
        list(GRID_INTERSECTIONS) if any(k.startswith("(") for k in traffic_input.keys())
        else list(DEFAULT_INTERSECTIONS)
    )

    # 1. Build exact 4-variable QUBO
    Q, offset, var_labels = build_binary_qubo(
        traffic_input=traffic_input,
        coord_weight=coord_weight,
        intersections=inter_list,
        symmetrize=False,
    )

    # 2. Convert to QuadraticProgram
    qp = qubo_to_quadratic_program(
        Q=Q,
        offset=offset,
        var_names=var_labels,
        problem_name="quantumflow_traffic_4var",
    )

    # 3. Execute genuine QAOA
    try:
        qaoa_output = execute_qaoa(
            qp=qp,
            p_layers=p_layers,
            shots=shots,
            maxiter=maxiter,
            seed=seed,
        )
        status = "ok"
        error_msg = None
    except Exception as exc:  # pylint: disable=broad-except
        return QuantumSolverResult(
            bitstring="0000",
            objective_value=float("inf"),
            status="error",
            runtime_ms=0.0,
            timing_plan={},
            solver_result=SolverResult(
                algorithm="qaoa",
                timing_plan={},
                cost=None,
                metrics={
                    "total_vehicles": 0,
                    "vehicles_served": 0,
                    "remaining_queue": 0,
                    "avg_wait_sec": 0.0,
                    "total_delay_sec": 0.0,
                    "runtime_ms": 0.0,
                },
                runtime_ms=0.0,
                status="error",
                error_msg=str(exc),
            ),
            samples=[],
            optimal_parameters=None,
            variable_names=var_labels,
            error_msg=str(exc),
            shots=shots,
            p_layers=p_layers,
            maxiter=maxiter,
            seed=seed,
        )

    bitstring = qaoa_output["bitstring"]
    runtime_ms = qaoa_output["runtime_ms"]
    objective_val = qaoa_output["fval"]

    # 4. Decode measured bitstring to TimingPlan
    timing_plan = decode_bitstring(bitstring, inter_list)
    validate_timing_plan(timing_plan, traffic_input)

    # 5. Evaluate against shared traffic model evaluator
    solver_res = evaluate_traffic(
        traffic_input=traffic_input,
        timing_plan=timing_plan,
        algorithm="qaoa",
        runtime_ms=runtime_ms,
        cost=objective_val,
    )

    return QuantumSolverResult(
        bitstring=bitstring,
        objective_value=objective_val,
        status=status,
        runtime_ms=runtime_ms,
        timing_plan=timing_plan,
        solver_result=solver_res,
        samples=qaoa_output["samples"],
        optimal_parameters=qaoa_output["optimal_parameters"],
        variable_names=var_labels,
        error_msg=error_msg,
        shots=shots,
        p_layers=p_layers,
        maxiter=maxiter,
        seed=seed,
    )


# ---------------------------------------------------------------------------
# CLI Execution & Standalone Demonstration
# ---------------------------------------------------------------------------
def main() -> None:
    """Run known small optimization example and then the traffic QUBO."""
    print("=" * 70)
    print("  QUANTUMFLOW — GENUINE QAOA QUANTUM SOLVER")
    print("  Local Quantum Simulator (Qiskit Aer) & Classical Optimizer (COBYLA)")
    print("=" * 70)

    # -----------------------------------------------------------------------
    # Step 1: Run Known Small Optimization Example
    # -----------------------------------------------------------------------
    print("\n[STEP 1] Running Known Small Optimization Example (2 Qubits)...")
    print("  Objective: minimize f(x0, x1) = -x0 - x1 + 2*x0*x1")
    print("  Analytical minimum: f = -1.0 at [0, 1] or [1, 0]")
    print("  Reproducible settings: p_layers=1, shots=1024, maxiter=50, seed=42")

    small_res = run_small_example(p_layers=1, shots=1024, maxiter=50, seed=42)

    print(f"  > Measured Bitstring:    '{small_res['bitstring']}' (x={small_res['best_x']})")
    print(f"  > Objective Value:       {small_res['fval']:.4f}")
    print(f"  > Optimal Ground State:  {'YES (SUCCESS)' if small_res['is_optimal'] else 'NO'}")
    print(f"  > Quantum Runtime:       {small_res['runtime_ms']:.1f} ms")
    print("  > Measurement Distribution:")
    for s in small_res["samples"]:
        print(f"      |{s['bitstring']}> : prob = {s['probability']:.4f}  (fval = {s['fval']:.1f})")

    # -----------------------------------------------------------------------
    # Step 2: Run 4-Variable Traffic QUBO
    # -----------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("[STEP 2] Running 4-Variable Traffic QUBO on Benchmark Snapshot...")
    from simulator.traffic_simulator import TrafficSimulator
    traffic = TrafficSimulator().get_traffic_input(as_grid=False)

    print("  Traffic Demand per Intersection:")
    for iid, counts in traffic.items():
        print(f"    Intersection {iid}: NS = {counts['ns_count']} veh, EW = {counts['ew_count']} veh")

    print("\n  Executing Genuine QAOA:")
    print("    Variables:           4 binary choices (x_A, x_B, x_C, x_D)")
    print("    Layers (p):          1")
    print("    Shots:               1024")
    print("    Optimizer:           COBYLA (maxiter=50)")
    print("    Quantum Simulator:   Qiskit Aer Sampler")
    print("    Seed:                42")

    traffic_res = solve_traffic_qubo(
        traffic_input=traffic,
        coord_weight=5.0,
        p_layers=1,
        shots=1024,
        maxiter=50,
        seed=42,
    )

    print(f"\n  > Best Measured Bitstring: '{traffic_res['bitstring']}'")
    print(f"  > Objective Value:         {traffic_res['objective_value']:.2f}")
    print(f"  > Execution Status:        {traffic_res['status']}")
    print(f"  > Wall-clock Runtime:      {traffic_res['runtime_ms']:.1f} ms")

    m = traffic_res["solver_result"]["metrics"]
    print("\n  > Evaluated Traffic Metrics (Shared Evaluator):")
    print(f"      Total Vehicles:    {m['total_vehicles']}")
    print(f"      Vehicles Served:   {m['vehicles_served']}")
    print(f"      Remaining Queue:   {m['remaining_queue']}")
    print(f"      Average Wait:      {m['avg_wait_sec']} s")
    print(f"      Total Delay:       {m['total_delay_sec']} s")

    print("\n  > Resulting Signal Timing Plan:")
    for iid, timing in traffic_res["timing_plan"].items():
        print(f"      Intersection {iid}: NS Green = {timing['ns_green']}s, EW Green = {timing['ew_green']}s")

    print("\n  > Top Measured Quantum States:")
    for i, s in enumerate(traffic_res["samples"][:5]):
        print(f"      #{i+1}: |{s['bitstring']}>  prob={s['probability']:.4f}  fval={s['fval']:.1f}")

    print("\n" + "=" * 70)
    print("  QAOA Execution Completed Successfully. No classical override used.")
    print("=" * 70)


if __name__ == "__main__":
    main()
