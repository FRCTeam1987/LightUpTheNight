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

        self.assertEqual(config.arms["left"].home_active_level, "LOW")
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
            config.motion.speed_offsets_us,
            {"slow": 35, "medium": 60, "fast": 90},
        )
        self.assertEqual(normal_motion.pulse_for("left", "forward", "slow"), 1535)
        self.assertEqual(normal_motion.pulse_for("left", "reverse", "slow"), 1465)
        self.assertEqual(normal_motion.pulse_for("right", "forward", "slow"), 1535)
        inverted_motion = replace(config.motion, invert_direction=True)
        self.assertEqual(inverted_motion.pulse_for("left", "forward", "slow"), 1465)
        self.assertEqual(inverted_motion.pulse_for("left", "reverse", "slow"), 1535)
        self.assertEqual(inverted_motion.pulse_for("right", "forward", "slow"), 1465)
        self.assertEqual(config.presets[0].speed, "slow")
        self.assertEqual(len(config.presets), 2)

    def test_every_speed_maps_to_expected_pulse_for_both_arms(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        config = load_config(project_root / "config" / "default.json")
        for inverted in (False, True):
            motion = replace(config.motion, invert_direction=inverted)
            for speed, offset in {"slow": 35, "medium": 60, "fast": 90}.items():
                sign = -1 if inverted else 1
                for arm in ("left", "right"):
                    self.assertEqual(
                        motion.pulse_for(arm, "forward", speed),
                        1500 + sign * offset,
                    )
                    self.assertEqual(
                        motion.pulse_for(arm, "reverse", speed),
                        1500 - sign * offset,
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
        self.assertGreater(config.gait.swing_duration_s, 0)

        raw = json.loads(source.read_text(encoding="utf-8"))
        del raw["gait"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            self.assertIsNone(load_config(path).gait)
            raw["gait"] = {
                "swing_duration_s": 0,
                "turnaround_pause_s": 0,
                "rehome_every_cycles": 0,
            }
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "swing_duration_s"):
                load_config(path)

    def test_homing_offset_is_optional_and_validated(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        raw = json.loads(
            (project_root / "config" / "default.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            raw["motion"].pop("homing_offset_us", None)
            path.write_text(json.dumps(raw), encoding="utf-8")
            self.assertIsNone(load_config(path).motion.homing_offset_us)
            raw["motion"]["homing_offset_us"] = 18
            path.write_text(json.dumps(raw), encoding="utf-8")
            motion = load_config(path).motion
            self.assertEqual(motion.homing_offset_us, 18)
            self.assertEqual(motion.homing_pulse_for("left"), 1518)  # inverted
            raw["motion"]["homing_offset_us"] = 0
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "homing_offset_us"):
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
