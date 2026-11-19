"""Find the smallest pulse offset that makes each arm move (the deadband edge).

Interactive: one arm at a time. For each offset from --start up to --stop (in
--step increments) it waits for Enter, drives that arm away from home for
--duration seconds, then back toward home for the same time, and asks whether
the arm moved. It stops at the first "y" and reports the offset per arm. An arm
driving toward home stops by itself when its own home switch trips. Run it
with `ssh -t` so it can read your answers.

Usage (needs root for PWM sysfs):
    sudo env PYTHONPATH=src python3 scripts/find_min_offset.py --config config/default.json
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from lightupthenight.config import ARM_NAMES, load_config


def drive(hardware, config, offset: int, toward_home: bool, duration: float, arms=ARM_NAMES) -> None:
    neutral = config.motion.neutral_pulse_us
    # pulse_for("reverse") is the homing direction; apply the same sign convention.
    sign = 1 if config.motion.invert_direction else -1
    direction_sign = sign if toward_home else -sign
    active = set(arms)
    if toward_home:
        for arm in arms:
            if hardware.is_home(arm):
                print(f"    {arm} already at home; not driven toward it")
                active.discard(arm)
    for arm in active:
        arm_offset = offset + (config.motion.right_arm_speed_adjustment_us if arm == "right" else 0)
        hardware.set_pulse_us(arm, neutral + direction_sign * arm_offset)
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline and active:
        if toward_home:
            for arm in list(active):
                if hardware.is_home(arm):
                    hardware.set_pulse_us(arm, neutral)
                    active.discard(arm)
                    print(f"    {arm} reached its home switch; stopped")
        time.sleep(0.005)
    for arm in arms:
        hardware.set_pulse_us(arm, neutral)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/default.json"))
    parser.add_argument("--start", type=int, default=28)
    parser.add_argument("--stop", type=int, default=40)
    parser.add_argument("--step", type=int, default=2)
    parser.add_argument("--duration", type=float, default=1.5)
    args = parser.parse_args()

    from lightupthenight.gpio_hardware import GpioHardware  # needs gpiozero (Pi only)

    config = load_config(args.config)
    hardware = GpioHardware(config)
    found: dict[str, int | None] = {arm: None for arm in ARM_NAMES}
    try:
        for arm in ARM_NAMES:
            print(f"--- {arm} arm only ---")
            for offset in range(args.start, args.stop + 1, args.step):
                input(f"{arm}: press Enter to try offset {offset} us (Ctrl-C to quit) ")
                drive(hardware, config, offset, False, args.duration, (arm,))
                time.sleep(0.5)
                drive(hardware, config, offset, True, args.duration, (arm,))
                if input(f"Did the {arm} arm move at {offset} us? [y/N] ").strip().lower() == "y":
                    found[arm] = offset
                    break
    except KeyboardInterrupt:
        print("interrupted")
    finally:
        hardware.close()
    for arm, offset in found.items():
        print(f"{arm}: first moved at {offset} us" if offset else f"{arm}: no movement recorded")
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
