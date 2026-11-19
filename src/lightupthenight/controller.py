"""Time-based motor controller for the alternating walking gait."""

from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import Protocol

from .config import ARM_NAMES, ArmName, AppConfig

logger = logging.getLogger(__name__)


class MotorHardware(Protocol):
    def set_pulse_us(self, arm: ArmName, pulse_us: int) -> None: ...

    def close(self) -> None: ...


class ControllerState(Enum):
    RESTING = auto()
    GAIT = auto()
    GAIT_PAUSE = auto()


# Each gait leg: (left direction, right direction, fraction of swing_duration_s).
_GAIT_LEGS = {
    "start": ("forward", "reverse", 0.5),
    "a": ("reverse", "forward", 1.0),
    "b": ("forward", "reverse", 1.0),
}
_GAIT_NEXT_LEG = {"start": "a", "a": "b", "b": "a"}


class ArmController:
    def __init__(self, config: AppConfig, hardware: MotorHardware) -> None:
        self.config = config
        self.hardware = hardware
        self.state = ControllerState.RESTING
        self._gait_leg = "start"
        self._gait_leg_started = 0.0
        self._gait_started = 0.0
        self._pause_until = 0.0

    def start(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._stop_all()
        if self.config.gait is not None:
            self._begin_gait(now)
            logger.info("Starting gait")

    def step(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        if self.state is ControllerState.GAIT:
            self._step_gait(now)
        elif self.state is ControllerState.GAIT_PAUSE:
            self._step_gait_pause(now)

    def run(self) -> None:
        self.start()
        while True:
            self.step()
            time.sleep(self.config.motion.control_period_s)

    def stop(self) -> None:
        self._stop_all()

    def _begin_gait(self, now: float) -> None:
        self.state = ControllerState.GAIT
        self._gait_leg = "start"
        self._gait_leg_started = now
        self._gait_started = now

    def _step_gait(self, now: float) -> None:
        gait = self.config.gait
        assert gait is not None
        if now - self._gait_started >= gait.active_duration_s:
            self._stop_all()
            self.state = ControllerState.GAIT_PAUSE
            self._pause_until = now + gait.pause_duration_s
            logger.info(
                "Gait active period complete; pausing for %.1f seconds",
                gait.pause_duration_s,
            )
            return

        left_direction, right_direction, fraction = _GAIT_LEGS[self._gait_leg]
        leg_duration = gait.swing_duration_s * fraction
        elapsed = now - self._gait_leg_started
        if elapsed < leg_duration:
            self.hardware.set_pulse_us(
                "left", self.config.motion.pulse_for("left", left_direction, "slow")
            )
            self.hardware.set_pulse_us(
                "right",
                self.config.motion.pulse_for("right", right_direction, "slow"),
            )
            return

        self._stop_all()
        if elapsed < leg_duration + gait.turnaround_pause_s:
            return

        self._gait_leg = _GAIT_NEXT_LEG[self._gait_leg]
        self._gait_leg_started = now

    def _step_gait_pause(self, now: float) -> None:
        if now >= self._pause_until:
            self._begin_gait(now)
            self._step_gait(now)

    def _stop_all(self) -> None:
        for arm in ARM_NAMES:
            self.hardware.set_pulse_us(arm, self.config.motion.neutral_pulse_us)
