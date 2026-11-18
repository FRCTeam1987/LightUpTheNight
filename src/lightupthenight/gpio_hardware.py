"""gpiozero adapter for SPARK MAX PWM inputs and normally-closed switches."""

from __future__ import annotations

import logging
import time

from gpiozero import Button

from .config import ARM_NAMES, ArmName, AppConfig
from .linux_pwm import LinuxPWMOutput

logger = logging.getLogger(__name__)


class GpioHardware:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.pwm_outputs: dict[ArmName, LinuxPWMOutput] = {}
        self.switches: dict[ArmName, Button] = {}
        self._closed = False
        try:
            for arm in ARM_NAMES:
                arm_config = config.arms[arm]
                self.pwm_outputs[arm] = LinuxPWMOutput(
                    chip=config.motion.pwm_chip,
                    channel=arm_config.pwm_channel,
                    period_ns=round(config.motion.frame_width_s * 1_000_000_000),
                    min_pulse_us=config.motion.min_pulse_us,
                    max_pulse_us=config.motion.max_pulse_us,
                    neutral_pulse_us=config.motion.neutral_pulse_us,
                )
                self.switches[arm] = Button(
                    arm_config.limit_pin,
                    pull_up=False,
                )
        except Exception:
            try:
                self.close()
            except Exception:
                logger.exception("Failed to release GPIO resources after initialization error")
            raise

    def is_home(self, arm: ArmName) -> bool:
        signal_is_high = self.switches[arm].is_pressed
        return signal_is_high == (self.config.arms[arm].home_active_level == "HIGH")

    def set_pulse_us(self, arm: ArmName, pulse_us: int) -> None:
        self.pwm_outputs[arm].set_pulse_us(pulse_us)

    def close(self) -> None:
        if self._closed:
            return
        first_error: Exception | None = None
        for arm, output in self.pwm_outputs.items():
            try:
                output.set_pulse_us(self.config.motion.neutral_pulse_us)
            except Exception as error:
                logger.exception("Failed to set %s PWM output to neutral", arm)
                first_error = first_error or error
        time.sleep(0.1)
        for device in (*self.switches.values(), *self.pwm_outputs.values()):
            try:
                device.close()
            except Exception as error:
                logger.exception("Failed to close GPIO/PWM device")
                first_error = first_error or error
        self._closed = True
        if first_error is not None:
            raise RuntimeError("Failed to safely close all hardware outputs") from first_error
