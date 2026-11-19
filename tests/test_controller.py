import random
import unittest
from dataclasses import replace

from lightupthenight.config import (
    ARM_NAMES,
    ArmCommand,
    ArmConfig,
    AppConfig,
    GaitConfig,
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


class GaitTests(unittest.TestCase):
    """Left/right gait loop. Test config: slow offset 10 (+10 on the right arm)."""

    def make(self, **gait_overrides) -> tuple[ArmController, FakeHardware]:
        gait = GaitConfig(
            swing_duration_s=2.0,
            turnaround_pause_s=0.0,
            rehome_every_cycles=0,
        )
        config = replace(make_config(), gait=replace(gait, **gait_overrides))
        hardware = FakeHardware()
        controller = ArmController(config, hardware)
        controller.start(now=0)
        hardware.home.update(left=True, right=True)
        controller.step(now=0.1)
        hardware.home.update(left=False, right=False)
        controller.step(now=1.2)  # left rest (1 s) done
        controller.step(now=2.2)  # right rest (2 s) done -> gait begins
        return controller, hardware

    def test_arms_swing_in_opposition_from_rest(self) -> None:
        controller, hardware = self.make()
        self.assertEqual(controller.state, ControllerState.GAIT)
        # start leg: left forward, right reverse (right arm has +10 adjustment)
        controller.step(now=2.3)
        self.assertEqual(hardware.pulses, {"left": 1510, "right": 1480})
        # start leg is a half swing (1.0 s); then leg "a" reverses both arms
        controller.step(now=3.3)
        controller.step(now=3.4)
        self.assertEqual(hardware.pulses, {"left": 1490, "right": 1520})
        # a full swing (2.0 s) later, leg "b" swings back
        controller.step(now=5.4)
        controller.step(now=5.5)
        self.assertEqual(hardware.pulses, {"left": 1510, "right": 1480})
        # and the loop keeps alternating
        controller.step(now=7.5)
        controller.step(now=7.6)
        self.assertEqual(hardware.pulses, {"left": 1490, "right": 1520})
        self.assertEqual(controller.state, ControllerState.GAIT)

    def test_arms_are_always_driven_in_opposite_directions(self) -> None:
        controller, hardware = self.make(turnaround_pause_s=0.2)
        now = 2.2
        for _ in range(600):
            now += 0.05
            controller.step(now=now)
            left, right = hardware.pulses["left"], hardware.pulses["right"]
            moving = (left != 1500) + (right != 1500)
            self.assertIn(moving, (0, 2))
            if moving:
                self.assertNotEqual(left > 1500, right > 1500)

    def test_turnaround_pause_holds_neutral_between_swings(self) -> None:
        controller, hardware = self.make(turnaround_pause_s=0.5)
        controller.step(now=3.3)  # start leg (1 s) finished
        self.assertEqual(hardware.pulses, {"left": 1500, "right": 1500})
        controller.step(now=3.7)
        self.assertEqual(hardware.pulses, {"left": 1500, "right": 1500})
        controller.step(now=3.8)  # pause over, next leg begins
        controller.step(now=3.9)
        self.assertEqual(hardware.pulses, {"left": 1490, "right": 1520})

    def test_limit_switch_during_gait_faults_and_recovers_into_gait(self) -> None:
        controller, hardware = self.make()
        hardware.home["right"] = True
        controller.step(now=2.5)
        self.assertEqual(controller.state, ControllerState.FAULT_PAUSE)
        self.assertEqual(hardware.pulses, {"left": 1500, "right": 1500})

    def test_periodic_rehome_after_configured_cycles(self) -> None:
        controller, hardware = self.make(rehome_every_cycles=1)
        controller.step(now=3.3)  # start -> a
        controller.step(now=5.4)  # a -> b
        self.assertEqual(controller.state, ControllerState.GAIT)
        controller.step(now=7.5)  # b complete: one full cycle -> re-home
        self.assertEqual(controller.state, ControllerState.HOMING)

    def test_no_gait_when_not_configured(self) -> None:
        hardware = FakeHardware()
        controller = ArmController(make_config(), hardware)
        controller.start(now=0)
        hardware.home.update(left=True, right=True)
        controller.step(now=0.1)
        hardware.home.update(left=False, right=False)
        controller.step(now=2.2)
        controller.step(now=3.0)
        self.assertEqual(controller.state, ControllerState.RESTING)


class IndependentSwitchTests(unittest.TestCase):
    """Each arm must react only to its own home switch."""

    def setUp(self) -> None:
        self.hardware = FakeHardware()
        self.controller = ArmController(make_config(), self.hardware)

    def test_homing_stops_only_the_arm_whose_switch_tripped(self) -> None:
        for tripped, other in (("right", "left"), ("left", "right")):
            hardware = FakeHardware()
            controller = ArmController(make_config(), hardware)
            controller.start(now=0)
            moving = dict(hardware.pulses)
            hardware.home[tripped] = True
            controller.step(now=0.5)
            self.assertEqual(hardware.pulses[tripped], 1500)
            self.assertEqual(hardware.pulses[other], moving[other])
            self.assertNotEqual(hardware.pulses[other], 1500)
            self.assertEqual(controller.state, ControllerState.HOMING)

    def test_fault_backs_off_only_the_tripped_arm(self) -> None:
        for tripped, other, expected in (
            ("right", "left", {"left": 1500, "right": 1520}),
            ("left", "right", {"left": 1510, "right": 1500}),
        ):
            hardware = FakeHardware()
            controller = ArmController(make_config(), hardware)
            controller.start(now=0)
            hardware.home.update(left=True, right=True)
            controller.step(now=0.1)
            hardware.home.update(left=False, right=False)
            controller.step(now=2.2)
            controller.step(now=3.0)
            controller._begin_preset(0, now=3.0)
            hardware.home[tripped] = True
            controller.step(now=3.1)
            self.assertEqual(controller.state, ControllerState.FAULT_PAUSE)
            controller.step(now=4.2)
            self.assertEqual(controller.state, ControllerState.FAULT_RELEASE)
            self.assertEqual(hardware.pulses, expected)
            self.assertEqual(hardware.pulses[other], 1500)

    def test_gait_trip_on_one_arm_stops_both_and_backs_off_only_that_arm(self) -> None:
        gait = GaitConfig(swing_duration_s=2.0, turnaround_pause_s=0.0, rehome_every_cycles=0)
        for tripped, expected in (
            ("right", {"left": 1500, "right": 1520}),
            ("left", {"left": 1510, "right": 1500}),
        ):
            hardware = FakeHardware()
            controller = ArmController(replace(make_config(), gait=gait), hardware)
            controller.start(now=0)
            hardware.home.update(left=True, right=True)
            controller.step(now=0.1)
            hardware.home.update(left=False, right=False)
            controller.step(now=2.2)
            controller.step(now=2.3)
            self.assertEqual(controller.state, ControllerState.GAIT)
            hardware.home[tripped] = True
            controller.step(now=2.5)
            self.assertEqual(hardware.pulses, {"left": 1500, "right": 1500})
            controller.step(now=3.6)
            self.assertEqual(controller.state, ControllerState.FAULT_RELEASE)
            self.assertEqual(hardware.pulses, expected)


class HomingSpeedTests(unittest.TestCase):
    def test_homing_uses_its_own_offset_and_other_moves_stay_slow(self) -> None:
        config = make_config()
        config = replace(config, motion=replace(config.motion, homing_offset_us=4))
        hardware = FakeHardware()
        controller = ArmController(config, hardware)
        controller.start(now=0)
        # slow offset is 10 (+10 right) but homing uses 4 (+10 right)
        self.assertEqual(hardware.pulses, {"left": 1496, "right": 1486})
        hardware.home.update(left=True, right=True)
        controller.step(now=0.1)
        hardware.home.update(left=False, right=False)
        controller.step(now=0.5)
        self.assertEqual(hardware.pulses, {"left": 1510, "right": 1520})  # rest move: slow

    def test_homing_offset_defaults_to_slow(self) -> None:
        motion = make_config().motion
        self.assertIsNone(motion.homing_offset_us)
        self.assertEqual(motion.homing_pulse_for("left"), motion.pulse_for("left", "reverse", "slow"))
        self.assertEqual(motion.homing_pulse_for("right"), motion.pulse_for("right", "reverse", "slow"))
        inverted = replace(motion, invert_direction=True)
        self.assertEqual(inverted.homing_pulse_for("left"), inverted.pulse_for("left", "reverse", "slow"))


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
