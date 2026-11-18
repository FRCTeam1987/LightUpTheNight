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
            {"slow": 5, "medium": 15, "fast": 30},
        )
        self.assertEqual(normal_motion.pulse_for("left", "forward", "slow"), 1505)
        self.assertEqual(normal_motion.pulse_for("left", "reverse", "slow"), 1495)
        self.assertEqual(normal_motion.pulse_for("right", "forward", "slow"), 1505)
        inverted_motion = replace(config.motion, invert_direction=True)
        self.assertEqual(inverted_motion.pulse_for("left", "forward", "slow"), 1495)
        self.assertEqual(inverted_motion.pulse_for("left", "reverse", "slow"), 1505)
        self.assertEqual(inverted_motion.pulse_for("right", "forward", "slow"), 1495)
        self.assertEqual(config.presets[0].speed, "slow")
        self.assertEqual(len(config.presets), 2)

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
