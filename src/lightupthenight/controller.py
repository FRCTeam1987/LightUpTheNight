"""Time-based motor controller and recoverable limit-switch fault handling."""

from __future__ import annotations

import logging
import random
import time
from enum import Enum, auto
from typing import Protocol

from .config import ARM_NAMES, ArmName, AppConfig, Preset

logger = logging.getLogger(__name__)


class MotorHardware(Protocol):
    def is_home(self, arm: ArmName) -> bool: ...

    def set_pulse_us(self, arm: ArmName, pulse_us: int) -> None: ...

    def close(self) -> None: ...


class ControllerState(Enum):
    HOMING = auto()
    MOVING_TO_REST = auto()
    RESTING = auto()
    SEQUENCING = auto()
    FAULT_PAUSE = auto()
    FAULT_RELEASE = auto()
    FAILED = auto()


class ArmController:
    def __init__(
        self,
        config: AppConfig,
        hardware: MotorHardware,
        *,
        random_source: random.Random | None = None,
    ) -> None:
        self.config = config
        self.hardware = hardware
        self.random = random_source or random.Random()
        self.state = ControllerState.HOMING
        self._homing_started: dict[ArmName, float] = {}
        self._homed: set[ArmName] = set()
        self._rest_started: float | None = None
        self._rested: set[ArmName] = set()
        self._preset: Preset | None = None
        self._preset_index = -1
        self._preset_started: float | None = None
        self._next_transition_at: float | None = None
        self._fault_pause_until: float | None = None
        self._release_targets: set[ArmName] = set()
        self._release_started: dict[ArmName, float] = {}

    def start(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._stop_all()
        self._begin_homing(now)
        self._step_homing(now)

    def step(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        if self.state is ControllerState.HOMING:
            self._step_homing(now)
        elif self.state is ControllerState.MOVING_TO_REST:
            self._step_moving_to_rest(now)
        elif self.state is ControllerState.SEQUENCING:
            self._step_sequencing(now)
        elif self.state is ControllerState.FAULT_PAUSE:
            self._step_fault_pause(now)
        elif self.state is ControllerState.FAULT_RELEASE:
            self._step_fault_release(now)
        elif self.state is ControllerState.FAILED:
            raise RuntimeError("controller is in a failed state")

    def run(self) -> None:
        self.start()
        while True:
            self.step()
            time.sleep(self.config.motion.control_period_s)

    def stop(self) -> None:
        self._stop_all()

    def _begin_homing(self, now: float) -> None:
        self.state = ControllerState.HOMING
        self._homing_started = {arm: now for arm in ARM_NAMES}
        self._homed.clear()
        self._rested.clear()
        self._preset = None
        self._preset_started = None
        self._next_transition_at = None
        for arm in ARM_NAMES:
            self.hardware.set_pulse_us(arm, self.config.motion.neutral_pulse_us)

    def _step_homing(self, now: float) -> None:
        for arm in ARM_NAMES:
            if arm in self._homed:
                continue
            if self.hardware.is_home(arm):
                self.hardware.set_pulse_us(arm, self.config.motion.neutral_pulse_us)
                self._homed.add(arm)
            elif now - self._homing_started[arm] >= self.config.motion.homing_timeout_s:
                self._fail(f"{arm} arm did not reach its home switch before timeout")
            else:
                self.hardware.set_pulse_us(
                    arm, self.config.motion.pulse_for(arm, "reverse", "slow")
                )

        if len(self._homed) == len(ARM_NAMES):
            self._begin_move_to_rest(now)

    def _begin_move_to_rest(self, now: float) -> None:
        self.state = ControllerState.MOVING_TO_REST
        self._rest_started = now
        self._rested.clear()

    def _step_moving_to_rest(self, now: float) -> None:
        assert self._rest_started is not None
        for arm in ARM_NAMES:
            if arm in self._rested:
                continue
            duration = self.config.arms[arm].rest_duration_s
            if now - self._rest_started >= duration:
                self.hardware.set_pulse_us(arm, self.config.motion.neutral_pulse_us)
                self._rested.add(arm)
            else:
                self.hardware.set_pulse_us(
                    arm, self.config.motion.pulse_for(arm, "forward", "slow")
                )

        if len(self._rested) == len(ARM_NAMES):
            self.state = ControllerState.RESTING

    def _begin_preset(self, index: int, now: float) -> None:
        self.state = ControllerState.SEQUENCING
        self._preset_index = index
        self._preset = self.config.presets[index]
        self._preset_started = now
        interval = self.random.uniform(
            self.config.motion.sequence_interval_min_s,
            self.config.motion.sequence_interval_max_s,
        )
        self._next_transition_at = now + interval
        for arm in ARM_NAMES:
            command = self._preset.arms[arm]
            pulse_us = (
                self.config.motion.pulse_for(
                    arm, command.direction, self._preset.speed
                )
                if command.duration_s > 0
                else self.config.motion.neutral_pulse_us
            )
            self.hardware.set_pulse_us(arm, pulse_us)

    def _step_sequencing(self, now: float) -> None:
        triggered = {arm for arm in ARM_NAMES if self.hardware.is_home(arm)}
        if triggered:
            self._begin_fault(now, triggered)
            return

        assert self._preset is not None
        assert self._preset_started is not None
        assert self._next_transition_at is not None
        move_complete = True
        for arm in ARM_NAMES:
            command = self._preset.arms[arm]
            if now - self._preset_started >= command.duration_s:
                self.hardware.set_pulse_us(arm, self.config.motion.neutral_pulse_us)
            else:
                move_complete = False
                self.hardware.set_pulse_us(
                    arm,
                    self.config.motion.pulse_for(
                        arm, command.direction, self._preset.speed
                    ),
                )

        if move_complete and now >= self._next_transition_at:
            next_index = (self._preset_index + 1) % len(self.config.presets)
            self._begin_preset(next_index, now)

    def _begin_fault(self, now: float, triggered: set[ArmName]) -> None:
        logger.warning(
            "Limit switch activated during preset operation (%s); stopping and recovering",
            ", ".join(sorted(triggered)),
        )
        self._stop_all()
        self.state = ControllerState.FAULT_PAUSE
        self._release_targets = set(triggered)
        self._fault_pause_until = now + self.config.motion.fault_pause_s

    def _step_fault_pause(self, now: float) -> None:
        assert self._fault_pause_until is not None
        self._release_targets = {
            arm for arm in self._release_targets if self.hardware.is_home(arm)
        }
        self._release_targets.update(
            arm for arm in ARM_NAMES if self.hardware.is_home(arm)
        )
        if now < self._fault_pause_until:
            return

        if not self._release_targets:
            self._begin_homing(now)
            self._step_homing(now)
            return

        self.state = ControllerState.FAULT_RELEASE
        self._release_started = {arm: now for arm in self._release_targets}
        for arm in self._release_targets:
            self.hardware.set_pulse_us(
                arm, self.config.motion.pulse_for(arm, "forward", "slow")
            )

    def _step_fault_release(self, now: float) -> None:
        new_targets = {
            arm
            for arm in ARM_NAMES
            if self.hardware.is_home(arm) and arm not in self._release_targets
        }
        for arm in new_targets:
            self._release_targets.add(arm)
            self._release_started[arm] = now
            self.hardware.set_pulse_us(
                arm, self.config.motion.pulse_for(arm, "forward", "slow")
            )
        for arm in tuple(self._release_targets):
            if not self.hardware.is_home(arm):
                self.hardware.set_pulse_us(arm, self.config.motion.neutral_pulse_us)
                self._release_targets.remove(arm)
            elif (
                now - self._release_started[arm]
                >= self.config.motion.switch_release_timeout_s
            ):
                self._fail(f"{arm} arm limit switch did not release before timeout")
            else:
                self.hardware.set_pulse_us(
                    arm, self.config.motion.pulse_for(arm, "forward", "slow")
                )

        if not self._release_targets:
            self._begin_homing(now)
            self._step_homing(now)

    def _stop_all(self) -> None:
        for arm in ARM_NAMES:
            self.hardware.set_pulse_us(arm, self.config.motion.neutral_pulse_us)

    def _fail(self, message: str) -> None:
        self._stop_all()
        self.state = ControllerState.FAILED
        raise RuntimeError(message)
