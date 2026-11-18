import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lightupthenight.linux_pwm import LinuxPWMOutput


class LinuxPWMOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sysfs_root = Path(self.temp_dir.name)
        chip_path = self.sysfs_root / "pwmchip0"
        chip_path.mkdir()
        (chip_path / "npwm").write_text("2", encoding="ascii")
        (chip_path / "export").touch()
        (chip_path / "unexport").touch()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def export_channel(self, output: LinuxPWMOutput) -> None:
        output.channel_path.mkdir()
        for attribute, value in (
            ("enable", "0"),
            ("polarity", "normal"),
            ("period", "0"),
            ("duty_cycle", "0"),
        ):
            (output.channel_path / attribute).write_text(value, encoding="ascii")
        output._exported = True

    def test_sets_period_neutral_and_updates_pulse_width(self) -> None:
        with patch.object(
            LinuxPWMOutput,
            "_export_channel",
            autospec=True,
            side_effect=self.export_channel,
        ), patch("lightupthenight.linux_pwm.time.sleep"):
            output = LinuxPWMOutput(
                chip=0,
                channel=1,
                period_ns=20_000_000,
                min_pulse_us=1000,
                max_pulse_us=2000,
                neutral_pulse_us=1500,
                sysfs_root=self.sysfs_root,
            )

            self.assertEqual(
                (output.channel_path / "period").read_text(encoding="ascii"),
                "20000000",
            )
            self.assertEqual(
                (output.channel_path / "duty_cycle").read_text(encoding="ascii"),
                "1500000",
            )
            self.assertEqual(
                (output.channel_path / "enable").read_text(encoding="ascii"),
                "1",
            )

            output.set_pulse_us(1650)
            self.assertEqual(
                (output.channel_path / "duty_cycle").read_text(encoding="ascii"),
                "1650000",
            )
            output.close()

        self.assertEqual(
            (output.channel_path / "duty_cycle").read_text(encoding="ascii"),
            "1500000",
        )
        self.assertEqual(
            (output.channel_path / "enable").read_text(encoding="ascii"), "0"
        )
        self.assertEqual(
            (self.sysfs_root / "pwmchip0" / "unexport").read_text(encoding="ascii"),
            "1",
        )

    def test_rejects_already_exported_channel(self) -> None:
        (self.sysfs_root / "pwmchip0" / "pwm1").mkdir()
        with self.assertRaisesRegex(RuntimeError, "already exported"):
            LinuxPWMOutput(
                chip=0,
                channel=1,
                period_ns=20_000_000,
                min_pulse_us=1000,
                max_pulse_us=2000,
                neutral_pulse_us=1500,
                sysfs_root=self.sysfs_root,
            )


if __name__ == "__main__":
    unittest.main()
