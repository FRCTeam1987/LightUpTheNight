import unittest
from dataclasses import replace

from lightupthenight.config import (
    ARM_NAMES,
    ArmConfig,
    AppConfig,
    GaitConfig,
    MotionConfig,
)
from lightupthenight.controller import ArmController, ControllerState


class FakeHardware:
    def __init__(self) -> None:
        self.pulses = {arm: 1500 for arm in ARM_NAMES}
        self.history: list[tuple[str, int]] = []

    def set_pulse_us(self, arm: str, pulse_us: int) -> None:
        self.pulses[arm] = pulse_us
        self.history.append((arm, pulse_us))

    def close(self) -> None:
        pass


def make_config(
    *,
    active_duration_s: float = 30.0,
    pause_duration_s: float = 60.0,
) -> AppConfig:
    arms = {
        "left": ArmConfig(18, 0, 23, "LOW"),
        "right": ArmConfig(19, 1, 24, "LOW"),
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
        sequence_interval_min_s=1.0,
        sequence_interval_max_s=1.0,
        control_period_s=0.01,
    )
    gait = GaitConfig(
        swing_duration_s=2.0,
        turnaround_pause_s=0.0,
        active_duration_s=active_duration_s,
        pause_duration_s=pause_duration_s,
    )
    return AppConfig(arms=arms, motion=motion, presets=(), gait=gait)


class GaitTests(unittest.TestCase):
    def make(self, **gait_overrides) -> tuple[ArmController, FakeHardware]:
        config = replace(make_config(), gait=replace(make_config().gait, **gait_overrides))
        hardware = FakeHardware()
        controller = ArmController(config, hardware)
        controller.start(now=0)
        return controller, hardware

    def test_start_enters_gait_without_homing_or_rest_motion(self) -> None:
        controller, hardware = self.make()
        self.assertEqual(controller.state, ControllerState.GAIT)
        self.assertEqual(hardware.pulses, {"left": 1500, "right": 1500})
        controller.step(now=0.1)
        self.assertEqual(hardware.pulses, {"left": 1510, "right": 1480})

    def test_gait_ignores_limit_switches(self) -> None:
        controller, hardware = self.make()
        controller.step(now=0.1)
        hardware.switches = {"left": True, "right": True}
        controller.step(now=0.2)
        self.assertEqual(controller.state, ControllerState.GAIT)
        self.assertEqual(hardware.pulses, {"left": 1510, "right": 1480})

    def test_arms_swing_in_opposition_and_alternate(self) -> None:
        controller, hardware = self.make(active_duration_s=20.0)
        controller.step(now=0.1)
        self.assertEqual(hardware.pulses, {"left": 1510, "right": 1480})
        controller.step(now=1.0)
        controller.step(now=1.1)
        self.assertEqual(hardware.pulses, {"left": 1490, "right": 1520})
        controller.step(now=3.1)
        controller.step(now=3.2)
        self.assertEqual(hardware.pulses, {"left": 1510, "right": 1480})

    def test_turnaround_pause_holds_neutral_between_swings(self) -> None:
        controller, hardware = self.make(turnaround_pause_s=0.5)
        controller.step(now=1.0)
        self.assertEqual(hardware.pulses, {"left": 1500, "right": 1500})
        controller.step(now=1.4)
        self.assertEqual(hardware.pulses, {"left": 1500, "right": 1500})
        controller.step(now=1.5)
        controller.step(now=1.6)
        self.assertEqual(hardware.pulses, {"left": 1490, "right": 1520})

    def test_active_duration_stops_both_motors_then_pauses(self) -> None:
        controller, hardware = self.make(active_duration_s=30.0, pause_duration_s=60.0)
        controller.step(now=0.1)
        controller.step(now=29.99)
        self.assertEqual(controller.state, ControllerState.GAIT)
        self.assertTrue(
            any(pulse != 1500 for _, pulse in hardware.history)
        )

        controller.step(now=30.0)
        self.assertEqual(controller.state, ControllerState.GAIT_PAUSE)
        self.assertEqual(hardware.pulses, {"left": 1500, "right": 1500})

        controller.step(now=89.99)
        self.assertEqual(controller.state, ControllerState.GAIT_PAUSE)
        self.assertEqual(hardware.pulses, {"left": 1500, "right": 1500})
        controller.step(now=90.0)
        self.assertEqual(controller.state, ControllerState.GAIT)
        self.assertEqual(hardware.pulses, {"left": 1510, "right": 1480})

    def test_pause_restarts_active_timer(self) -> None:
        controller, hardware = self.make(active_duration_s=2.0, pause_duration_s=3.0)
        controller.step(now=2.0)
        self.assertEqual(controller.state, ControllerState.GAIT_PAUSE)
        controller.step(now=5.0)
        controller.step(now=6.99)
        self.assertEqual(controller.state, ControllerState.GAIT)
        controller.step(now=7.0)
        self.assertEqual(controller.state, ControllerState.GAIT_PAUSE)
        self.assertEqual(hardware.pulses, {"left": 1500, "right": 1500})

    def test_no_gait_configuration_leaves_motors_neutral(self) -> None:
        hardware = FakeHardware()
        controller = ArmController(replace(make_config(), gait=None), hardware)
        controller.start(now=0)
        controller.step(now=10)
        self.assertEqual(controller.state, ControllerState.RESTING)
        self.assertEqual(hardware.pulses, {"left": 1500, "right": 1500})


if __name__ == "__main__":
    unittest.main()
