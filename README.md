# Light Up The Night

A Python controller for two SPARK MAX motor controllers connected to Raspberry Pi GPIO. It sends servo-style PWM pulses and estimates arm travel from elapsed time; there are no position sensors other than the two home limit switches.

## Hardware and safety

- Each SPARK MAX must be configured to accept its factory-default PWM control range: 1000 µs full reverse, 1500 µs neutral, and 2000 µs full forward. Confirm the controller's PWM and signal-voltage requirements against its documentation before wiring.
- The sample pin assignments and motion values are placeholders. Validate the wiring and tune pulse widths and durations with the mechanism safely supported and clear of people and obstructions. A pulse away from neutral commands motor motion.
- Do not power motors from the Raspberry Pi. Use suitable motor power, a common signal ground where required, and electrical protection appropriate to the mechanism.
- The sample switch configuration treats LOW as the home signal and does not enable an internal GPIO pull resistor. If a switch is powered from the Pi's 5 V pin, its signal must pass through a suitable level shifter or other properly designed, protected interface before reaching a GPIO. Never connect 5 V directly to a Pi GPIO; GPIO inputs are not 5 V tolerant. The interface must provide a defined GPIO-side level in both switch states, remain within 0–3.3 V, and produce LOW at home. Change `home_active_level` to match the GPIO-side circuit.
- Timed movement is only an estimate. It is not a substitute for position feedback, physical stops, or independent emergency-stop protection.

## Configuration

Edit [`config/default.json`](config/default.json) before running:

- `arms.*.pwm_pin` and `arms.*.limit_pin` are BCM GPIO numbers and must all be unique.
- `home_active_level` selects the GPIO level that means the arm is at its limit.
- `homing_reverse_pulse_us`, `rest_forward_pulse_us`, and `fault_release_pulse_us` are per-arm speed commands.
- `rest_duration_s` is the per-arm timed move from home to the straight-down rest position.
- Each preset provides a per-arm `pulse_us` speed command and `duration_s`. Tune these separately to synchronize the arms.
- The SPARK MAX factory deadband is centered around 1500 µs. Sample movement commands are deliberately outside that deadband; confirm the configured deadband and choose appropriate speeds for your mechanism.
- `sequence_interval_min_s` and `sequence_interval_max_s` select a random interval for each preset. The next preset starts only after both arms finish their current timed move and that interval has elapsed. Presets repeat in listed order.
- Homing and switch-release timeouts stop the motors and raise an error if a switch is not reached or released. A normal-operation switch activation stops both arms, waits `fault_pause_s`, moves only triggered arms forward until their switches release, and homes both arms again.

The sample values are illustrative only; confirm actual speed, direction, and run time on the mechanism before unattended operation.

## Python versions

The project requires Python 3.13, which is the default `python3` version provided by Raspberry Pi OS Trixie. CI is configured to test Python 3.13, 3.14, and 3.15.

To confirm the interpreter on the Pi:

```sh
python3 --version
```

## Run on a Raspberry Pi

Use Raspberry Pi OS Trixie's default Python 3.13. From the project root:

```sh
sudo apt install python3-venv
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
python -m lightupthenight --config config/default.json
```

The controller uses `gpiozero`'s selected pin factory. Ensure the GPIO backend appropriate to the installed Raspberry Pi OS is available. Press Ctrl-C to stop; the controller commands neutral before closing GPIO resources.

## Start at boot with systemd

1. Copy the project to `/opt/light-up-the-night`, create its virtual environment, and install it as above.
2. Copy the edited configuration to `/etc/lightupthenight/config.json`.
3. Review `deploy/lightupthenight.service`; change `User`, paths, and permissions for the target Pi.
4. Install and start the service:

   ```sh
   sudo install -m 0644 deploy/lightupthenight.service /etc/systemd/system/lightupthenight.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now lightupthenight.service
   ```

Check status and logs with `systemctl status lightupthenight.service` and `journalctl -u lightupthenight.service`. The unit does not automatically restart after an error, so inspect the mechanism before manually restarting it.

## Tests

Run the hardware-independent controller tests with:

```sh
python3 -m unittest discover -s tests -v
```
