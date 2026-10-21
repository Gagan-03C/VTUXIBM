"""
QuantumFlow — Traffic Environment Simulator
Team Lead (Person A) · Phase 1, Hours 1-2
"""

import random
import math
from typing import Dict, List, Tuple


class TrafficGrid:
    """
    Represents an N×N intersection grid.
    Each cell is an intersection node; edges are road segments.
    """

    def __init__(self, grid_size: int = 4, seed: int = 42):
        if grid_size < 2 or grid_size > 10:
            raise ValueError("grid_size must be between 2 and 10.")
        self.grid_size = grid_size
        self.seed = seed
        self.rng = random.Random(seed)
        # 0 = empty intersection, 1 = occupied
        self.grid: List[List[int]] = [[0] * grid_size for _ in range(grid_size)]
        self.vehicles: List[Dict] = []
        self.congestion_map: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Vehicle management
    # ------------------------------------------------------------------
    def generate_vehicles(self, num_vehicles: int) -> List[Dict]:
        """Randomly place vehicles on the grid."""
        self.vehicles = []
        for i in range(num_vehicles):
            row = self.rng.randint(0, self.grid_size - 1)
            col = self.rng.randint(0, self.grid_size - 1)
            direction = self.rng.choice(["N", "S", "E", "W"])
            self.vehicles.append({"id": i, "row": row, "col": col, "direction": direction})
        return self.vehicles

    def step(self, time_steps: int = 1) -> None:
        """Advance simulation by `time_steps` ticks, moving vehicles."""
        for _ in range(time_steps):
            for v in self.vehicles:
                dr, dc = {"N": (-1, 0), "S": (1, 0), "E": (0, 1), "W": (0, -1)}[v["direction"]]
                new_r = (v["row"] + dr) % self.grid_size
                new_c = (v["col"] + dc) % self.grid_size
                v["row"], v["col"] = new_r, new_c
                # Randomly change direction with 10% probability
                if self.rng.random() < 0.1:
                    v["direction"] = self.rng.choice(["N", "S", "E", "W"])

    # ------------------------------------------------------------------
    # Congestion calculation
    # ------------------------------------------------------------------
    def compute_congestion(self) -> Dict[str, float]:
        """
        Compute congestion score per intersection.
        Score = vehicles_at_cell / max_capacity (capped at 1.0).
        Max capacity is a soft constant of 3 vehicles per intersection.
        """
        max_capacity = 3
        counts: Dict[str, int] = {}
        for v in self.vehicles:
            key = f"({v['row']},{v['col']})"
            counts[key] = counts.get(key, 0) + 1

        self.congestion_map = {}
        for row in range(self.grid_size):
            for col in range(self.grid_size):
                key = f"({row},{col})"
                count = counts.get(key, 0)
                self.congestion_map[key] = min(count / max_capacity, 1.0)

        return self.congestion_map

    def get_grid_state(self) -> List[List[int]]:
        """Return occupancy grid (1 if any vehicle present, else 0)."""
        state = [[0] * self.grid_size for _ in range(self.grid_size)]
        for v in self.vehicles:
            state[v["row"]][v["col"]] = 1
        self.grid = state
        return state

    # ------------------------------------------------------------------
    # Full simulation run
    # ------------------------------------------------------------------
    def run(self, num_vehicles: int = 20, time_steps: int = 10) -> Dict:
        """Run a full simulation and return snapshot."""
        self.generate_vehicles(num_vehicles)
        self.step(time_steps)
        grid = self.get_grid_state()
        congestion = self.compute_congestion()

        return {
            "grid_size": self.grid_size,
            "grid": grid,
            "vehicle_positions": self.vehicles,
            "congestion_map": congestion,
        }
