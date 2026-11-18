import unittest
from pathlib import Path

from lightupthenight.config import load_config


class ConfigTests(unittest.TestCase):
    def test_sample_config_is_valid(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        config = load_config(project_root / "config" / "default.json")

        self.assertEqual(config.arms["left"].home_active_level, "LOW")
        self.assertEqual(config.motion.neutral_pulse_us, 1500)
        self.assertEqual(len(config.presets), 2)


if __name__ == "__main__":
    unittest.main()
