"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
import signal
from pathlib import Path

from .config import load_config
from .controller import ArmController


def _raise_keyboard_interrupt(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


def install_signal_handlers() -> None:
    """Make `systemctl stop` (SIGTERM) shut down like Ctrl-C.

    Without this, SIGTERM would kill the process without commanding neutral,
    and kernel PWM would keep sending the last pulse.
    """
    signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)


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
    from .gpio_hardware import GpioHardware  # needs gpiozero (Pi only)

    install_signal_handlers()
    config = load_config(args.config)
    hardware = GpioHardware(config)
    controller = ArmController(config, hardware)
    try:
        controller.run()
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Controller stopped by signal or user")
    finally:
        try:
            controller.stop()
        finally:
            hardware.close()


if __name__ == "__main__":
    main()
