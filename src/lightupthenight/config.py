"""Configuration loading and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ArmName = Literal["left", "right"]
ARM_NAMES: tuple[ArmName, ArmName] = ("left", "right")
Speed = Literal["slow", "medium", "fast"]
SPEED_NAMES: tuple[Speed, Speed, Speed] = ("slow", "medium", "fast")
Direction = Literal["forward", "reverse"]


@dataclass(frozen=True)
class ArmConfig:
    pwm_pin: int
    limit_pin: int
    home_active_level: Literal["LOW", "HIGH"]
    rest_duration_s: float


@dataclass(frozen=True)
class ArmCommand:
    direction: Direction
    duration_s: float


@dataclass(frozen=True)
class Preset:
    name: str
    speed: Speed
    arms: dict[ArmName, ArmCommand]


@dataclass(frozen=True)
class MotionConfig:
    min_pulse_us: int
    max_pulse_us: int
    neutral_pulse_us: int
    speed_offsets_us: dict[Speed, int]
    right_arm_speed_adjustment_us: int
    frame_width_s: float
    homing_timeout_s: float
    fault_pause_s: float
    switch_release_timeout_s: float
    sequence_interval_min_s: float
    sequence_interval_max_s: float
    control_period_s: float

    def pulse_for(self, arm: ArmName, direction: Direction, speed: Speed) -> int:
        offset = self.speed_offsets_us[speed]
        if arm == "right":
            offset += self.right_arm_speed_adjustment_us
        direction_sign = 1 if direction == "forward" else -1
        return self.neutral_pulse_us + direction_sign * offset


@dataclass(frozen=True)
class AppConfig:
    arms: dict[ArmName, ArmConfig]
    motion: MotionConfig
    presets: tuple[Preset, ...]


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _number(
    values: dict[str, object],
    key: str,
    name: str,
    *,
    integer: bool = False,
) -> int | float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}.{key} must be a number")
    if integer and not isinstance(value, int):
        raise ValueError(f"{name}.{key} must be an integer")
    return value


def _positive_number(
    values: dict[str, object],
    key: str,
    name: str,
    *,
    allow_zero: bool = False,
) -> float:
    value = _number(values, key, name)
    if value < 0 or (value == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{name}.{key} must be {qualifier}")
    return float(value)


def _pulse(values: dict[str, object], key: str, name: str) -> int:
    return int(_number(values, key, name, integer=True))


def _speed(value: object, name: str) -> Speed:
    if value == "slow":
        return "slow"
    if value == "medium":
        return "medium"
    if value == "fast":
        return "fast"
    raise ValueError(f"{name} must be slow, medium, or fast")


def _direction(value: object, name: str) -> Direction:
    if value == "forward":
        return "forward"
    if value == "reverse":
        return "reverse"
    raise ValueError(f"{name} must be forward or reverse")


def load_config(path: Path) -> AppConfig:
    """Load a JSON config file and reject unsafe or inconsistent settings."""
    with path.open(encoding="utf-8") as config_file:
        raw = _object(json.load(config_file), "config")

    raw_motion = _object(raw.get("motion"), "motion")
    raw_speed_offsets = _object(
        raw_motion.get("speed_offsets_us"), "motion.speed_offsets_us"
    )
    speed_offsets = {
        speed: _pulse(raw_speed_offsets, speed, "motion.speed_offsets_us")
        for speed in SPEED_NAMES
    }
    motion = MotionConfig(
        min_pulse_us=_pulse(raw_motion, "min_pulse_us", "motion"),
        max_pulse_us=_pulse(raw_motion, "max_pulse_us", "motion"),
        neutral_pulse_us=_pulse(raw_motion, "neutral_pulse_us", "motion"),
        speed_offsets_us=speed_offsets,
        right_arm_speed_adjustment_us=int(
            _number(
                raw_motion,
                "right_arm_speed_adjustment_us",
                "motion",
                integer=True,
            )
        ),
        frame_width_s=_positive_number(raw_motion, "frame_width_s", "motion"),
        homing_timeout_s=_positive_number(raw_motion, "homing_timeout_s", "motion"),
        fault_pause_s=_positive_number(
            raw_motion, "fault_pause_s", "motion", allow_zero=True
        ),
        switch_release_timeout_s=_positive_number(
            raw_motion, "switch_release_timeout_s", "motion"
        ),
        sequence_interval_min_s=_positive_number(
            raw_motion, "sequence_interval_min_s", "motion", allow_zero=True
        ),
        sequence_interval_max_s=_positive_number(
            raw_motion, "sequence_interval_max_s", "motion", allow_zero=True
        ),
        control_period_s=_positive_number(raw_motion, "control_period_s", "motion"),
    )
    if motion.min_pulse_us >= motion.max_pulse_us:
        raise ValueError("motion.min_pulse_us must be less than max_pulse_us")
    if not motion.min_pulse_us <= motion.neutral_pulse_us <= motion.max_pulse_us:
        raise ValueError("motion.neutral_pulse_us must be within the pulse range")
    if any(motion.speed_offsets_us[speed] <= 0 for speed in SPEED_NAMES):
        raise ValueError("motion.speed_offsets_us values must be positive")
    if not (
        motion.speed_offsets_us["slow"]
        < motion.speed_offsets_us["medium"]
        < motion.speed_offsets_us["fast"]
    ):
        raise ValueError(
            "motion.speed_offsets_us values must increase from slow to fast"
        )
    for arm_name in ARM_NAMES:
        for speed in SPEED_NAMES:
            offset = motion.speed_offsets_us[speed]
            if arm_name == "right":
                offset += motion.right_arm_speed_adjustment_us
            if offset < 0:
                raise ValueError(
                    "motion.right_arm_speed_adjustment_us must not reverse "
                    "the right arm direction"
                )
            for direction in ("forward", "reverse"):
                pulse_us = motion.neutral_pulse_us + (
                    offset if direction == "forward" else -offset
                )
                _validate_pulse(
                    pulse_us, motion, f"motion.{speed}_{arm_name}_{direction}"
                )
    if motion.sequence_interval_min_s > motion.sequence_interval_max_s:
        raise ValueError(
            "motion.sequence_interval_min_s must not exceed sequence_interval_max_s"
        )
    if motion.frame_width_s * 1_000_000 <= motion.max_pulse_us:
        raise ValueError("motion.frame_width_s must exceed the maximum pulse width")

    raw_arms = _object(raw.get("arms"), "arms")
    if set(raw_arms) != set(ARM_NAMES):
        raise ValueError("arms must define exactly 'left' and 'right'")

    arms: dict[ArmName, ArmConfig] = {}
    configured_pins: set[int] = set()
    for arm_name in ARM_NAMES:
        values = _object(raw_arms[arm_name], f"arms.{arm_name}")
        pwm_pin = _number(values, "pwm_pin", f"arms.{arm_name}", integer=True)
        limit_pin = _number(values, "limit_pin", f"arms.{arm_name}", integer=True)
        for pin_name, pin in (("pwm_pin", pwm_pin), ("limit_pin", limit_pin)):
            if not 0 <= pin <= 27:
                raise ValueError(f"arms.{arm_name}.{pin_name} must be a BCM pin from 0 to 27")
            if pin in configured_pins:
                raise ValueError(f"GPIO BCM pin {pin} is assigned more than once")
            configured_pins.add(pin)

        home_active_level = values.get("home_active_level")
        if home_active_level not in ("LOW", "HIGH"):
            raise ValueError(f"arms.{arm_name}.home_active_level must be LOW or HIGH")

        arm_config = ArmConfig(
            pwm_pin=int(pwm_pin),
            limit_pin=int(limit_pin),
            home_active_level=home_active_level,
            rest_duration_s=_positive_number(
                values, "rest_duration_s", f"arms.{arm_name}", allow_zero=True
            ),
        )
        arms[arm_name] = arm_config

    raw_presets = raw.get("presets")
    if not isinstance(raw_presets, list) or not raw_presets:
        raise ValueError("presets must be a non-empty array")
    presets: list[Preset] = []
    preset_names: set[str] = set()
    for index, raw_preset in enumerate(raw_presets):
        preset_data = _object(raw_preset, f"presets[{index}]")
        name = preset_data.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"presets[{index}].name must be a non-empty string")
        if name in preset_names:
            raise ValueError(f"preset name {name!r} is duplicated")
        preset_names.add(name)
        speed = _speed(preset_data.get("speed"), f"presets[{index}].speed")
        raw_commands = _object(preset_data.get("arms"), f"presets[{index}].arms")
        if set(raw_commands) != set(ARM_NAMES):
            raise ValueError(f"presets[{index}].arms must define left and right")
        commands: dict[ArmName, ArmCommand] = {}
        for arm_name in ARM_NAMES:
            command = _object(
                raw_commands[arm_name], f"presets[{index}].arms.{arm_name}"
            )
            direction = _direction(
                command.get("direction"),
                f"presets[{index}].arms.{arm_name}.direction",
            )
            commands[arm_name] = ArmCommand(
                direction=direction,
                duration_s=_positive_number(
                    command,
                    "duration_s",
                    f"presets[{index}].arms.{arm_name}",
                    allow_zero=True,
                ),
            )
        presets.append(Preset(name=name, speed=speed, arms=commands))

    return AppConfig(arms=arms, motion=motion, presets=tuple(presets))


def _validate_pulse(pulse_us: int, motion: MotionConfig, name: str) -> None:
    if not motion.min_pulse_us <= pulse_us <= motion.max_pulse_us:
        raise ValueError(
            f"{name} must be between {motion.min_pulse_us} and "
            f"{motion.max_pulse_us} microseconds"
        )
