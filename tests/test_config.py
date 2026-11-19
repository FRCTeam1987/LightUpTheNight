import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from lightupthenight.config import load_config


class ConfigTests(unittest.TestCase):
    def test_sample_config_is_valid(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        config = load_config(project_root / "config" / "default.json")

        self.assertEqual(config.arms["left"].pwm_pin, 18)
        self.assertEqual(config.arms["left"].pwm_channel, 0)
        self.assertEqual(config.arms["left"].limit_pin, 27)
        self.assertEqual(config.arms["right"].pwm_pin, 19)
        self.assertEqual(config.arms["right"].pwm_channel, 1)
        self.assertEqual(config.arms["right"].limit_pin, 22)
        self.assertEqual(config.motion.pwm_chip, 0)
        self.assertEqual(config.motion.neutral_pulse_us, 1500)
        self.assertIsInstance(config.motion.invert_direction, bool)
        normal_motion = replace(config.motion, invert_direction=False)
        self.assertEqual(
            set(config.motion.speed_offsets_us), {"slow", "medium", "fast"}
        )
        self.assertEqual(
            normal_motion.pulse_for("left", "forward", "slow"),
            1500 + config.motion.speed_offsets_us["slow"],
        )
        self.assertEqual(
            normal_motion.pulse_for("left", "reverse", "slow"),
            1500 - config.motion.speed_offsets_us["slow"],
        )
        self.assertEqual(
            normal_motion.pulse_for("right", "forward", "slow"),
            1500
            + config.motion.speed_offsets_us["slow"]
            + config.motion.right_arm_speed_adjustment_us,
        )
        inverted_motion = replace(config.motion, invert_direction=True)
        self.assertEqual(
            inverted_motion.pulse_for("left", "forward", "slow"),
            1500 - config.motion.speed_offsets_us["slow"],
        )
        self.assertEqual(
            inverted_motion.pulse_for("left", "reverse", "slow"),
            1500 + config.motion.speed_offsets_us["slow"],
        )
        self.assertEqual(
            inverted_motion.pulse_for("right", "forward", "slow"),
            1500
            - config.motion.speed_offsets_us["slow"]
            - config.motion.right_arm_speed_adjustment_us,
        )
        self.assertEqual(config.presets[0].speed, "slow")
        self.assertEqual(len(config.presets), 2)

    def test_every_speed_maps_to_expected_pulse_for_both_arms(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        config = load_config(project_root / "config" / "default.json")
        for inverted in (False, True):
            motion = replace(config.motion, invert_direction=inverted)
            for speed, offset in config.motion.speed_offsets_us.items():
                sign = -1 if inverted else 1
                for arm in ("left", "right"):
                    arm_offset = offset + (
                        config.motion.right_arm_speed_adjustment_us
                        if arm == "right"
                        else 0
                    )
                    self.assertEqual(
                        motion.pulse_for(arm, "forward", speed),
                        1500 + sign * arm_offset,
                    )
                    self.assertEqual(
                        motion.pulse_for(arm, "reverse", speed),
                        1500 - sign * arm_offset,
                    )
                    for direction in ("forward", "reverse"):
                        pulse = motion.pulse_for(arm, direction, speed)
                        self.assertTrue(
                            motion.min_pulse_us <= pulse <= motion.max_pulse_us
                        )
        self.assertLess(
            config.motion.speed_offsets_us["slow"],
            config.motion.speed_offsets_us["medium"],
        )
        self.assertLess(
            config.motion.speed_offsets_us["medium"],
            config.motion.speed_offsets_us["fast"],
        )

    def test_gait_section_is_loaded_and_optional(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        source = project_root / "config" / "default.json"
        config = load_config(source)
        self.assertIsNotNone(config.gait)
        self.assertEqual(config.gait.active_duration_s, 30)
        self.assertEqual(config.gait.pause_duration_s, 60)

        raw = json.loads(source.read_text(encoding="utf-8"))
        del raw["gait"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            self.assertIsNone(load_config(path).gait)
            raw["gait"] = {
                "swing_duration_s": 0,
                "turnaround_pause_s": 0,
                "active_duration_s": 30,
                "pause_duration_s": 60,
            }
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "swing_duration_s"):
                load_config(path)

    def test_gait_active_and_pause_durations_must_be_positive(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        raw = json.loads(
            (project_root / "config" / "default.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            raw["gait"]["active_duration_s"] = 0
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "active_duration_s"):
                load_config(path)
            raw["gait"]["active_duration_s"] = 30
            raw["gait"]["pause_duration_s"] = 0
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "pause_duration_s"):
                load_config(path)

    def test_invert_direction_is_loaded_from_config(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        source = project_root / "config" / "default.json"
        raw = json.loads(source.read_text(encoding="utf-8"))
        raw["motion"]["invert_direction"] = True

        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            config = load_config(config_path)

        self.assertTrue(config.motion.invert_direction)

    def test_rejects_pwm_pin_channel_mismatch(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        source = project_root / "config" / "default.json"
        raw = json.loads(source.read_text(encoding="utf-8"))
        raw["arms"]["left"]["pwm_channel"] = 1

        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must use PWM channel"):
                load_config(config_path)


if __name__ == "__main__":
    unittest.main()
