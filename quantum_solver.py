"""
QuantumFlow — Genuine QAOA Quantum Solver
Root convenience module and CLI runner.
"""

from quantum.quantum_solver import (
    QAOAMeasurementSample,
    QuantumSolverResult,
    execute_qaoa,
    main,
    qubo_to_quadratic_program,
    run_small_example,
    solve_traffic_qubo,
)

__all__ = [
    "QAOAMeasurementSample",
    "QuantumSolverResult",
    "execute_qaoa",
    "main",
    "qubo_to_quadratic_program",
    "run_small_example",
    "solve_traffic_qubo",
]

if __name__ == "__main__":
    main()
