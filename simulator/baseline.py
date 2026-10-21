"""
QuantumFlow — Fixed-Time Signal Controller
simulator/baseline.py  ·  Owner: Team Lead

Equal-split baseline: every intersection gets 30 s North-South green and
30 s East-West green in a 60 s cycle. Independent of queue lengths.

Returns a TimingPlan in the same key format as the supplied TrafficInput
(named A–D or grid '(r,c)'). Does not mutate simulator state or data shapes.
"""

from __future__ import annotations

from shared.types import ApproachTiming, TrafficInput, TimingPlan
from shared.validators import (
    CYCLE_SEC,
    MAX_GREEN,
    MIN_GREEN,
    validate_timing_plan,
    validate_traffic_input,
)

NS_GREEN_FIXED = CYCLE_SEC // 2  # 30 s
EW_GREEN_FIXED = CYCLE_SEC // 2  # 30 s


def _validate_green_split(ns_green: int, ew_green: int, cycle_sec: int) -> None:
    """Reject green times that violate cycle or per-approach limits."""
    for name, value in (("ns_green", ns_green), ("ew_green", ew_green)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(
                f"{name} must be an integer, got {type(value).__name__}."
            )
        if not (MIN_GREEN <= value <= MAX_GREEN):
            raise ValueError(
                f"{name}: {value}s is outside [{MIN_GREEN}, {MAX_GREEN}]."
            )
    total = ns_green + ew_green
    if total != cycle_sec:
        raise ValueError(
            f"ns_green + ew_green = {total}s, must equal CYCLE_SEC={cycle_sec}s."
        )


def fixed_time_plan(
    traffic_input: TrafficInput,
    ns_green: int = NS_GREEN_FIXED,
    ew_green: int = EW_GREEN_FIXED,
    cycle_sec: int = CYCLE_SEC,
) -> TimingPlan:
    """
    Build a fixed-time TimingPlan for every intersection in traffic_input.

    Default split is 30 s NS / 30 s EW. Queue lengths are ignored.

    Args:
        traffic_input: TrafficInput — keys must match the simulator format.
        ns_green:      North-South green seconds (default 30).
        ew_green:      East-West green seconds (default 30).
        cycle_sec:     Cycle length in seconds (default 60).

    Returns:
        TimingPlan with one ApproachTiming per intersection.

    Raises:
        ValueError: if traffic_input is invalid, or the green split violates
            cycle / MIN_GREEN / MAX_GREEN constraints.
    """
    validate_traffic_input(traffic_input)
    _validate_green_split(ns_green, ew_green, cycle_sec)

    timing_plan: TimingPlan = {
        iid: ApproachTiming(ns_green=ns_green, ew_green=ew_green)
        for iid in traffic_input
    }
    validate_timing_plan(timing_plan, traffic_input)
    return timing_plan


class FixedTimeController:
    """Fixed-time controller with a configurable equal-cycle split."""

    def __init__(
        self,
        ns_green: int = NS_GREEN_FIXED,
        ew_green: int = EW_GREEN_FIXED,
        cycle_sec: int = CYCLE_SEC,
    ) -> None:
        _validate_green_split(ns_green, ew_green, cycle_sec)
        self.ns_green = ns_green
        self.ew_green = ew_green
        self.cycle_sec = cycle_sec

    def plan(self, traffic_input: TrafficInput) -> TimingPlan:
        """Return a validated TimingPlan for the given traffic snapshot."""
        return fixed_time_plan(
            traffic_input,
            ns_green=self.ns_green,
            ew_green=self.ew_green,
            cycle_sec=self.cycle_sec,
        )
