import importlib.util
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from lightupthenight.config import ARM_NAMES, load_config

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "speed_check.py"
spec = importlib.util.spec_from_file_location("speed_check", SCRIPT)
speed_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(speed_check)


class FakeHardware:
    def __init__(self) -> None:
        self.home = {arm: False for arm in ARM_NAMES}
        self.pulses = {arm: 1500 for arm in ARM_NAMES}

    def is_home(self, arm: str) -> bool:
        return self.home[arm]

    def set_pulse_us(self, arm: str, pulse_us: int) -> None:
        self.pulses[arm] = pulse_us


class SpeedCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.config = load_config(root / "config" / "default.json")
        self.hardware = FakeHardware()
        self.driven: dict[str, list[int]] = {arm: [] for arm in ARM_NAMES}
        original = self.hardware.set_pulse_us

        def record(arm: str, pulse_us: int) -> None:
            self.driven[arm].append(pulse_us)
            original(arm, pulse_us)

        self.hardware.set_pulse_us = record

    def run_move(self, direction: str, speed: str = "slow"):
        with redirect_stdout(io.StringIO()):
            return speed_check.move(
                self.hardware,
                self.config,
                direction,
                speed,
                0.2,
                read_duty=lambda hw, arm: hw.pulses[arm],
            )

    def test_forward_move_ignores_a_tripped_switch(self) -> None:
        self.hardware.home["right"] = True
        matched, reached = self.run_move("forward")
        self.assertTrue(matched)
        self.assertEqual(reached, [])
        for arm in ARM_NAMES:
            self.assertIn(1465, self.driven[arm])  # inverted: forward = 1500 - 35

    def test_reverse_stops_only_the_arm_whose_switch_trips(self) -> None:
        self.hardware.home["right"] = True
        matched, reached = self.run_move("reverse")
        self.assertEqual(reached, ["right"])
        self.assertNotIn(1535, self.driven["right"])  # never driven toward home
        self.assertIn(1535, self.driven["left"])  # left kept going
        self.assertEqual(self.hardware.pulses, {"left": 1500, "right": 1500})

    def test_left_trip_does_not_stop_right(self) -> None:
        self.hardware.home["left"] = True
        _, reached = self.run_move("reverse")
        self.assertEqual(reached, ["left"])
        self.assertIn(1535, self.driven["right"])
        self.assertNotIn(1535, self.driven["left"])

    def test_pulse_widths_for_every_speed_both_directions(self) -> None:
        for speed, offset in {"slow": 35, "medium": 60, "fast": 90}.items():
            self.driven = {arm: [] for arm in ARM_NAMES}
            self.run_move("forward", speed)
            self.run_move("reverse", speed)
            for arm in ARM_NAMES:
                self.assertIn(1500 - offset, self.driven[arm])
                self.assertIn(1500 + offset, self.driven[arm])


if __name__ == "__main__":
    unittest.main()
