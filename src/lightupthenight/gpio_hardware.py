"""gpiozero adapter for SPARK MAX PWM inputs and normally-closed switches."""

from __future__ import annotations

import logging
import time

from gpiozero import Button, Servo

from .config import ARM_NAMES, ArmName, AppConfig

logger = logging.getLogger(__name__)


class GpioHardware:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.servos: dict[ArmName, Servo] = {}
        self.switches: dict[ArmName, Button] = {}
        self._closed = False
        try:
            for arm in ARM_NAMES:
                arm_config = config.arms[arm]
                self.servos[arm] = Servo(
                    arm_config.pwm_pin,
                    initial_value=self._pulse_to_value(
                        config.motion.neutral_pulse_us
                    ),
                    min_pulse_width=config.motion.min_pulse_us / 1_000_000,
                    max_pulse_width=config.motion.max_pulse_us / 1_000_000,
                    frame_width=config.motion.frame_width_s,
                )
                self.switches[arm] = Button(
                    arm_config.limit_pin,
                    pull_up=None,
                    active_state=arm_config.home_active_level == "HIGH",
                )
        except Exception:
            try:
                self.close()
            except Exception:
                logger.exception("Failed to release GPIO resources after initialization error")
            raise

    def is_home(self, arm: ArmName) -> bool:
        return self.switches[arm].is_pressed

    def set_pulse_us(self, arm: ArmName, pulse_us: int) -> None:
        self.servos[arm].value = self._pulse_to_value(pulse_us)

    def close(self) -> None:
        if self._closed:
            return
        neutral_value = self._pulse_to_value(self.config.motion.neutral_pulse_us)
        for servo in self.servos.values():
            servo.value = neutral_value
        time.sleep(0.1)
        for device in (*self.switches.values(), *self.servos.values()):
            device.close()
        self._closed = True

    def _pulse_to_value(self, pulse_us: int) -> float:
        minimum = self.config.motion.min_pulse_us
        maximum = self.config.motion.max_pulse_us
        if not minimum <= pulse_us <= maximum:
            raise ValueError(f"PWM pulse must be between {minimum} and {maximum} microseconds")
        return 2 * (pulse_us - minimum) / (maximum - minimum) - 1
