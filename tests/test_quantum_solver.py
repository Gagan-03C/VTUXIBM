"""
QuantumFlow — Test Suite: Genuine QAOA Quantum Solver
tests/test_quantum_solver.py  ·  Owner: Quantum Engineer

Validates:
  1. Execution of genuine QAOA on small known optimization example with analytical minimum.
  2. Conversion of 4-variable traffic QUBO into Qiskit QuadraticProgram.
  3. Execution of genuine QAOA on 4-variable traffic QUBO using local Aer simulator.
  4. Preservation of variable ordering (x_A, x_B, x_C, x_D).
  5. Decoded timing plan satisfies cycle (60 s) and green duration (15–45 s) constraints.
  6. Reproducibility using seed settings.
  7. Architectural constraints (no Flask imports).
"""

from __future__ import annotations

import sys
import numpy as np
import pytest

from quantum.binary_qubo import build_binary_qubo
from quantum.quantum_solver import (
    QuantumSolverResult,
    execute_qaoa,
    qubo_to_quadratic_program,
    run_small_example,
    solve_traffic_qubo,
)
from shared.types import ApproachCounts, TrafficInput
from shared.validators import validate_timing_plan, validate_traffic_input
from simulator.traffic_simulator import TrafficSimulator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def benchmark_traffic() -> TrafficInput:
    """Benchmark traffic from TrafficSimulator (A=45/12, B=30/20, C=10/40, D=25/15)."""
    return TrafficSimulator().get_traffic_input(as_grid=False)


@pytest.fixture
def grid_traffic() -> TrafficInput:
    """Same traffic in 2x2 grid coordinate format."""
    return TrafficSimulator().get_traffic_input(as_grid=True)


# ---------------------------------------------------------------------------
# 1. Known Small Optimization Example Tests
# ---------------------------------------------------------------------------
class TestKnownSmallExample:
    """Verify QAOA performance on analytically known 2-variable problem."""

    def test_small_example_finds_analytical_ground_state(self):
        res = run_small_example(p_layers=1, shots=1024, maxiter=50, seed=42)
        assert res["fval"] == -1.0
        assert res["best_x"] in ([0, 1], [1, 0])
        assert res["bitstring"] in ("01", "10")
        assert res["is_optimal"] is True
        assert res["runtime_ms"] > 0.0

    def test_small_example_measurement_distribution(self):
        res = run_small_example(p_layers=1, shots=1024, maxiter=50, seed=42)
        samples = res["samples"]
        assert len(samples) == 4

        # Total probability must sum to ~1.0
        prob_sum = sum(s["probability"] for s in samples)
        assert abs(prob_sum - 1.0) < 1e-4

        # Top states should be the degenerate ground states |01> and |10>
        top_two_bitstrings = {samples[0]["bitstring"], samples[1]["bitstring"]}
        assert top_two_bitstrings == {"01", "10"}

    def test_reproducibility_with_seed(self):
        res1 = run_small_example(p_layers=1, shots=512, maxiter=30, seed=123)
        res2 = run_small_example(p_layers=1, shots=512, maxiter=30, seed=123)
        assert res1["bitstring"] == res2["bitstring"]
        assert res1["fval"] == res2["fval"]
        assert len(res1["samples"]) == len(res2["samples"])
        for s1, s2 in zip(res1["samples"], res2["samples"]):
            assert s1["bitstring"] == s2["bitstring"]
            assert s1["fval"] == s2["fval"]


# ---------------------------------------------------------------------------
# 2. QUBO to QuadraticProgram Conversion Tests
# ---------------------------------------------------------------------------
class TestQUBOToQuadraticProgram:
    """Verify matrix conversion preserves linear, quadratic, and constant terms."""

    def test_upper_triangular_qubo_conversion(self, benchmark_traffic):
        Q, offset, labels = build_binary_qubo(benchmark_traffic, coord_weight=5.0, symmetrize=False)
        qp = qubo_to_quadratic_program(Q, offset, labels)

        assert qp.get_num_binary_vars() == 4
        assert [v.name for v in qp.variables] == labels
        assert abs(qp.objective.constant - offset) < 1e-9

        # Linear coefficients match diagonal
        for i, name in enumerate(labels):
            assert abs(qp.objective.linear[name] - Q[i, i]) < 1e-9

    def test_symmetric_qubo_conversion_yields_identical_qp(self, benchmark_traffic):
        Q_upper, offset_upper, labels = build_binary_qubo(benchmark_traffic, coord_weight=5.0, symmetrize=False)
        Q_sym, offset_sym, _ = build_binary_qubo(benchmark_traffic, coord_weight=5.0, symmetrize=True)

        qp_upper = qubo_to_quadratic_program(Q_upper, offset_upper, labels)
        qp_sym = qubo_to_quadratic_program(Q_sym, offset_sym, labels)

        assert qp_upper.objective.constant == qp_sym.objective.constant
        assert qp_upper.objective.linear.to_dict() == qp_sym.objective.linear.to_dict()
        assert qp_upper.objective.quadratic.to_dict() == qp_sym.objective.quadratic.to_dict()

    def test_dimension_mismatch_raises(self):
        Q = np.zeros((3, 3))
        with pytest.raises(ValueError, match="does not match"):
            qubo_to_quadratic_program(Q, 0.0, ["x0", "x1", "x2", "x3"])


# ---------------------------------------------------------------------------
# 3. Traffic QUBO QAOA Execution Tests
# ---------------------------------------------------------------------------
class TestSolveTrafficQUBO:
    """Verify genuine QAOA execution on the 4-variable traffic problem."""

    def test_solve_traffic_qubo_success(self, benchmark_traffic):
        res = solve_traffic_qubo(
            traffic_input=benchmark_traffic,
            coord_weight=5.0,
            p_layers=1,
            shots=512,
            maxiter=30,
            seed=42,
        )

        assert res["status"] == "ok"
        assert res["error_msg"] is None
        assert len(res["bitstring"]) == 4
        assert set(res["bitstring"]).issubset({"0", "1"})
        assert res["runtime_ms"] > 0.0
        assert isinstance(res["objective_value"], float)

        # Variable names must preserve order
        assert res["variable_names"] == ["x_A", "x_B", "x_C", "x_D"]

        # Timing plan must strictly validate
        validate_timing_plan(res["timing_plan"], benchmark_traffic)
        for iid in ("A", "B", "C", "D"):
            assert iid in res["timing_plan"]
            timing = res["timing_plan"][iid]
            assert timing["ns_green"] + timing["ew_green"] == 60
            assert 15 <= timing["ns_green"] <= 45
            assert 15 <= timing["ew_green"] <= 45

        # Solver result metrics
        m = res["solver_result"]["metrics"]
        assert m["total_vehicles"] == 197
        assert 0 <= m["vehicles_served"] <= 197
        assert m["remaining_queue"] == 197 - m["vehicles_served"]
        assert m["avg_wait_sec"] >= 0.0

    def test_solve_traffic_qubo_with_grid_input(self, grid_traffic):
        res = solve_traffic_qubo(
            traffic_input=grid_traffic,
            coord_weight=0.0,
            p_layers=1,
            shots=512,
            maxiter=30,
            seed=42,
        )
        assert res["status"] == "ok"
        validate_timing_plan(res["timing_plan"], grid_traffic)
        assert set(res["timing_plan"].keys()) == {"(0,0)", "(0,1)", "(1,0)", "(1,1)"}

    def test_solve_traffic_qubo_p2_layers(self, benchmark_traffic):
        res = solve_traffic_qubo(
            traffic_input=benchmark_traffic,
            coord_weight=0.0,
            p_layers=2,
            shots=256,
            maxiter=20,
            seed=42,
        )
        assert res["status"] == "ok"
        assert len(res["bitstring"]) == 4
        validate_timing_plan(res["timing_plan"], benchmark_traffic)

    def test_invalid_traffic_input_raises_error(self):
        with pytest.raises(ValueError):
            solve_traffic_qubo({})


# ---------------------------------------------------------------------------
# 4. Architecture and File Ownership Constraints
# ---------------------------------------------------------------------------
class TestQuantumSolverArchitecture:
    """Verify architectural boundaries and forbidden import checks."""

    def test_no_flask_in_quantum_solver(self):
        import quantum.quantum_solver as qs_mod
        with open(qs_mod.__file__, "r", encoding="utf-8") as f:
            content = f.read()
        assert "flask" not in content, "quantum_solver.py must NOT import flask"

    def test_root_quantum_solver_no_flask(self):
        with open("quantum_solver.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "flask" not in content, "Root quantum_solver.py must NOT import flask"
