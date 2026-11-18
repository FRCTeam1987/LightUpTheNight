"""Linux sysfs PWM channel control."""

from __future__ import annotations

import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class LinuxPWMOutput:
    def __init__(
        self,
        chip: int,
        channel: int,
        period_ns: int,
        min_pulse_us: int,
        max_pulse_us: int,
        neutral_pulse_us: int,
        *,
        sysfs_root: Path = Path("/sys/class/pwm"),
    ) -> None:
        self.chip_path = sysfs_root / f"pwmchip{chip}"
        self.channel_path = self.chip_path / f"pwm{channel}"
        self.channel = channel
        self.period_ns = period_ns
        self.min_pulse_ns = min_pulse_us * 1000
        self.max_pulse_ns = max_pulse_us * 1000
        self.neutral_pulse_ns = neutral_pulse_us * 1000
        self._exported = False
        self._closed = False

        if not self.chip_path.is_dir():
            raise RuntimeError(f"Kernel PWM chip is unavailable: {self.chip_path}")
        channel_count = int((self.chip_path / "npwm").read_text(encoding="ascii"))
        if not 0 <= channel < channel_count:
            raise ValueError(
                f"PWM channel {channel} is unavailable on {self.chip_path} "
                f"(channel count: {channel_count})"
            )
        if self.channel_path.exists():
            raise RuntimeError(
                f"PWM channel is already exported: {self.channel_path}; "
                "check for another process or reboot to release a stale channel"
            )

        try:
            self._export_channel()
            self._write_attribute("enable", "0")
            polarity_path = self.channel_path / "polarity"
            if polarity_path.exists():
                self._write_attribute("polarity", "normal")
            self._write_attribute("period", str(period_ns))
            self._write_attribute("duty_cycle", "0")
            self.set_pulse_us(neutral_pulse_us)
            self._write_attribute("enable", "1")
        except Exception:
            if self._exported:
                try:
                    self._release_channel()
                except Exception:
                    logger.exception(
                        "Failed to release PWM channel %s after initialization error",
                        self.channel_path,
                    )
            raise

    def set_pulse_us(self, pulse_us: int) -> None:
        if self._closed:
            raise RuntimeError("PWM output is closed")
        if not self.min_pulse_ns <= pulse_us * 1000 <= self.max_pulse_ns:
            raise ValueError(
                f"PWM pulse must be between {self.min_pulse_ns // 1000} and "
                f"{self.max_pulse_ns // 1000} microseconds"
            )
        pulse_ns = pulse_us * 1000
        if pulse_ns >= self.period_ns:
            raise ValueError("PWM pulse width must be less than the PWM period")
        self._write_attribute("duty_cycle", str(pulse_ns))

    def close(self) -> None:
        if self._closed:
            return
        try:
            self.set_pulse_us(self.neutral_pulse_ns // 1000)
            time.sleep(0.1)
        finally:
            self._release_channel()
            self._closed = True

    def _export_channel(self) -> None:
        self._write_path(self.chip_path / "export", str(self.channel))
        self._exported = True
        deadline = time.monotonic() + 1.0
        while not self.channel_path.exists():
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Kernel did not create PWM channel {self.channel_path}"
                )
            time.sleep(0.01)

    def _release_channel(self) -> None:
        if not self._exported:
            return
        try:
            self._write_attribute("enable", "0")
        finally:
            self._write_path(self.chip_path / "unexport", str(self.channel))
            self._exported = False

    def _write_attribute(self, name: str, value: str) -> None:
        self._write_path(self.channel_path / name, value)

    @staticmethod
    def _write_path(path: Path, value: str) -> None:
        try:
            with path.open("w", encoding="ascii") as attribute:
                attribute.write(value)
        except OSError as error:
            raise RuntimeError(
                f"Cannot write kernel PWM attribute {path}: {error}. "
                "Check PWM sysfs permissions and that no other process owns it."
            ) from error
