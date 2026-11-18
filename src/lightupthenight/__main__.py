"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .config import load_config
from .controller import ArmController
from .gpio_hardware import GpioHardware


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the two-arm motor controller")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/default.json"),
        help="path to the controller JSON configuration",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = load_config(args.config)
    hardware = GpioHardware(config)
    controller = ArmController(config, hardware)
    try:
        controller.run()
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Controller stopped by user")
    finally:
        try:
            controller.stop()
        finally:
            hardware.close()


if __name__ == "__main__":
    main()
