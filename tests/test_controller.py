import random
import unittest

from lightupthenight.config import (
    ARM_NAMES,
    ArmCommand,
    ArmConfig,
    AppConfig,
    MotionConfig,
    Preset,
)
from lightupthenight.controller import ArmController, ControllerState


class FakeHardware:
    def __init__(self) -> None:
        self.home = {arm: False for arm in ARM_NAMES}
        self.pulses = {arm: 1500 for arm in ARM_NAMES}
        self.history: list[tuple[str, int]] = []

    def is_home(self, arm: str) -> bool:
        return self.home[arm]

    def set_pulse_us(self, arm: str, pulse_us: int) -> None:
        self.pulses[arm] = pulse_us
        self.history.append((arm, pulse_us))

    def close(self) -> None:
        pass


def make_config() -> AppConfig:
    arms = {
        "left": ArmConfig(18, 0, 23, "LOW", 1.0),
        "right": ArmConfig(19, 1, 24, "LOW", 2.0),
    }
    motion = MotionConfig(
        pwm_chip=0,
        min_pulse_us=1000,
        max_pulse_us=2000,
        neutral_pulse_us=1500,
        speed_offsets_us={"slow": 10, "medium": 50, "fast": 100},
        right_arm_speed_adjustment_us=10,
        invert_direction=False,
        frame_width_s=0.02,
        homing_timeout_s=5.0,
        fault_pause_s=1.0,
        switch_release_timeout_s=2.0,
        sequence_interval_min_s=1.0,
        sequence_interval_max_s=1.0,
        control_period_s=0.01,
    )
    presets = (
        Preset(
            "first",
            "fast",
            {
                "left": ArmCommand("forward", 2.0),
                "right": ArmCommand("forward", 3.5),
            },
        ),
        Preset(
            "second",
            "fast",
            {
                "left": ArmCommand("reverse", 1.0),
                "right": ArmCommand("reverse", 1.0),
            },
        ),
    )
    return AppConfig(arms=arms, motion=motion, presets=presets)


class ArmControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.hardware = FakeHardware()
        self.controller = ArmController(
            make_config(), self.hardware, random_source=random.Random(1)
        )

    def enter_sequence(self) -> None:
        self.controller.start(now=0)
        self.hardware.home.update(left=True, right=True)
        self.controller.step(now=0.1)
        self.assertEqual(self.controller.state, ControllerState.MOVING_TO_REST)
        self.hardware.home.update(left=False, right=False)
        self.controller.step(now=1.1)
        self.assertEqual(self.hardware.pulses["left"], 1500)
        self.controller.step(now=2.1)
        self.assertEqual(self.controller.state, ControllerState.RESTING)
        self.controller._begin_preset(0, now=2.1)
        self.assertEqual(self.controller.state, ControllerState.SEQUENCING)

    def test_homes_both_then_positions_arms_for_rest(self) -> None:
        self.controller.start(now=0)
        self.assertEqual(self.hardware.pulses, {"left": 1490, "right": 1480})

        self.hardware.home["left"] = True
        self.controller.step(now=0.5)
        self.assertEqual(self.hardware.pulses["left"], 1500)
        self.assertEqual(self.hardware.pulses["right"], 1480)

        self.hardware.home["right"] = True
        self.controller.step(now=1.0)
        self.assertEqual(self.controller.state, ControllerState.MOVING_TO_REST)
        self.hardware.home.update(left=False, right=False)
        self.controller.step(now=1.5)
        self.assertEqual(self.hardware.pulses, {"left": 1510, "right": 1520})
        self.controller.step(now=2.0)
        self.assertEqual(self.hardware.pulses["left"], 1500)
        self.assertEqual(self.hardware.pulses["right"], 1520)
        self.controller.step(now=3.0)
        self.assertEqual(self.controller.state, ControllerState.RESTING)
        self.assertEqual(self.hardware.pulses, {"left": 1500, "right": 1500})
        self.controller.step(now=4.0)
        self.assertEqual(self.controller.state, ControllerState.RESTING)
        self.assertEqual(self.hardware.pulses, {"left": 1500, "right": 1500})

    def test_preset_switch_waits_for_move_and_interval(self) -> None:
        self.enter_sequence()
        self.controller.step(now=3.2)
        self.assertEqual(self.hardware.pulses, {"left": 1600, "right": 1610})
        self.controller.step(now=5.1)
        self.assertEqual(self.hardware.pulses, {"left": 1500, "right": 1610})
        self.controller.step(now=6.1)
        self.assertEqual(self.controller.state, ControllerState.SEQUENCING)
        self.assertEqual(self.hardware.pulses, {"left": 1400, "right": 1390})

    def test_limit_fault_stops_then_releases_and_rehomes(self) -> None:
        self.enter_sequence()
        self.hardware.home["left"] = True
        self.controller.step(now=3.2)
        self.assertEqual(self.controller.state, ControllerState.FAULT_PAUSE)
        self.assertEqual(self.hardware.pulses, {"left": 1500, "right": 1500})

        self.controller.step(now=4.19)
        self.assertEqual(self.controller.state, ControllerState.FAULT_PAUSE)
        self.controller.step(now=4.2)
        self.assertEqual(self.controller.state, ControllerState.FAULT_RELEASE)
        self.assertEqual(self.hardware.pulses, {"left": 1510, "right": 1500})

        self.hardware.home["left"] = False
        self.controller.step(now=4.3)
        self.assertEqual(self.controller.state, ControllerState.HOMING)
        self.assertEqual(self.hardware.pulses, {"left": 1490, "right": 1480})

    def test_homing_timeout_stops_motors_and_raises(self) -> None:
        self.controller.start(now=0)
        with self.assertRaisesRegex(RuntimeError, "left arm did not reach"):
            self.controller.step(now=5.0)
        self.assertEqual(self.controller.state, ControllerState.FAILED)
        self.assertEqual(self.hardware.pulses, {"left": 1500, "right": 1500})

    def test_switch_release_timeout_stops_motors_and_raises(self) -> None:
        self.enter_sequence()
        self.hardware.home["left"] = True
        self.controller.step(now=3.2)
        self.controller.step(now=4.2)
        with self.assertRaisesRegex(RuntimeError, "left arm limit switch did not release"):
            self.controller.step(now=6.2)
        self.assertEqual(self.controller.state, ControllerState.FAILED)
        self.assertEqual(self.hardware.pulses, {"left": 1500, "right": 1500})


if __name__ == "__main__":
    unittest.main()
