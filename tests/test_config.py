import unittest
from pathlib import Path

from lightupthenight.config import load_config


class ConfigTests(unittest.TestCase):
    def test_sample_config_is_valid(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        config = load_config(project_root / "config" / "default.json")

        self.assertEqual(config.arms["left"].home_active_level, "LOW")
        self.assertEqual(config.arms["left"].pwm_pin, 13)
        self.assertEqual(config.arms["left"].limit_pin, 27)
        self.assertEqual(config.arms["right"].pwm_pin, 19)
        self.assertEqual(config.arms["right"].limit_pin, 22)
        self.assertEqual(config.motion.neutral_pulse_us, 1500)
        self.assertEqual(
            config.motion.speed_offsets_us,
            {"slow": 5, "medium": 15, "fast": 30},
        )
        self.assertEqual(config.motion.pulse_for("left", "reverse", "slow"), 1495)
        self.assertEqual(config.motion.pulse_for("right", "forward", "slow"), 1505)
        self.assertEqual(config.presets[0].speed, "slow")
        self.assertEqual(len(config.presets), 2)


if __name__ == "__main__":
    unittest.main()
