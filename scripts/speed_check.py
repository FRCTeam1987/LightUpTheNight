"""Hardware check of the slow / medium / fast speed levels.

Runs on the Pi with the arms near their rest position. For each speed it drives
both arms forward (away from home) for a short time, then in reverse (toward
home) for the same time. It reads each PWM channel's duty cycle back from sysfs
to prove the expected pulse width is really being output.

Each arm reacts to its own home switch only: an arm driving toward home stops
when its own switch trips while the other arm keeps going. A tripped switch
never blocks a forward move, because that moves the arm off the switch.
Ctrl-C stops both arms.

Usage (needs root for PWM sysfs):
    sudo env PYTHONPATH=src python3 scripts/speed_check.py --config config/default.json
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import TYPE_CHECKING

from lightupthenight.config import ARM_NAMES, load_config

if TYPE_CHECKING:
    from lightupthenight.gpio_hardware import GpioHardware

SPEEDS = ("slow", "medium", "fast")


def read_duty_us(hardware: GpioHardware, arm: str) -> int:
    path = hardware.pwm_outputs[arm].channel_path / "duty_cycle"
    return int(path.read_text(encoding="ascii")) // 1000


def move(
    hardware,
    config,
    direction: str,
    speed: str,
    duration: float,
    *,
    read_duty=read_duty_us,
) -> tuple[bool, list[str]]:
    """Drive both arms for `duration` seconds.

    Returns (pulses_matched, arms_that_reached_home). An arm moving in reverse
    (toward home) is stopped as soon as its own switch trips.
    """
    neutral = config.motion.neutral_pulse_us
    expected = {arm: config.motion.pulse_for(arm, direction, speed) for arm in ARM_NAMES}
    active = set(ARM_NAMES)
    reached_home: list[str] = []
    matched = True

    if direction == "reverse":
        for arm in ARM_NAMES:
            if hardware.is_home(arm):
                print(f"    {arm:5s} already at home; not driven toward it")
                hardware.set_pulse_us(arm, neutral)
                active.discard(arm)
                reached_home.append(arm)
    for arm in active:
        hardware.set_pulse_us(arm, expected[arm])

    time.sleep(0.05)
    for arm in sorted(active, key=ARM_NAMES.index):
        actual = read_duty(hardware, arm)
        status = "OK" if actual == expected[arm] else "MISMATCH"
        if actual != expected[arm]:
            matched = False
        print(f"    {arm:5s} commanded {expected[arm]} us, sysfs duty {actual} us  [{status}]")

    deadline = time.monotonic() + duration
    while time.monotonic() < deadline and active:
        if direction == "reverse":
            for arm in list(active):
                if hardware.is_home(arm):
                    hardware.set_pulse_us(arm, neutral)
                    active.discard(arm)
                    reached_home.append(arm)
                    print(f"    {arm:5s} reached its home switch; stopped (other arm continues)")
        time.sleep(0.005)
    for arm in ARM_NAMES:
        hardware.set_pulse_us(arm, neutral)
    return matched, reached_home


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/default.json"))
    parser.add_argument("--duration", type=float, default=1.0, help="seconds per move")
    parser.add_argument("--pause", type=float, default=1.5, help="seconds between moves")
    args = parser.parse_args()

    from lightupthenight.gpio_hardware import GpioHardware  # needs gpiozero (Pi only)

    config = load_config(args.config)
    hardware = GpioHardware(config)
    passed = True
    notes: list[str] = []
    try:
        for arm in ARM_NAMES:
            if hardware.is_home(arm):
                print(f"note: {arm} arm starts on its home switch (forward moves leave it)")
        for speed in SPEEDS:
            offset = config.motion.speed_offsets_us[speed]
            print(f"{speed} (offset {offset} us)")
            for direction in ("forward", "reverse"):
                print(f"  {direction} for {args.duration:.1f} s")
                matched, reached_home = move(hardware, config, direction, speed, args.duration)
                passed = passed and matched
                for arm in reached_home:
                    notes.append(f"{arm} reached home during {speed} {direction}")
                time.sleep(args.pause)
    except KeyboardInterrupt:
        print("interrupted")
        passed = False
    finally:
        hardware.close()
    for note in notes:
        print(f"note: {note}")
    print("PASS: all pulses matched" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
