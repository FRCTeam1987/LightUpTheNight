# Light Up The Night

A Python controller for two SPARK MAX motor controllers connected to Raspberry Pi GPIO. It sends servo-style PWM pulses and estimates arm travel from elapsed time; there are no position sensors other than the two home limit switches.

## Hardware and safety

- Each SPARK MAX must be configured to accept its factory-default PWM control range: 1000 µs full reverse, 1500 µs neutral, and 2000 µs full forward. Confirm the controller's PWM and signal-voltage requirements against its documentation before wiring.
- The sample pin assignments and motion values are placeholders. Validate the wiring and tune pulse widths and durations with the mechanism safely supported and clear of people and obstructions. A pulse away from neutral commands motor motion.
- Do not power motors from the Raspberry Pi. Use suitable motor power, a common signal ground where required, and electrical protection appropriate to the mechanism.
- The limit switches connect the Pi's 3.3 V (physical pin 17) through their normally-closed contacts to the GPIO inputs. The active-LOW setup uses internal pull-downs: the input is HIGH while the contact is closed and LOW when the switch opens. A broken wire also reads LOW and intentionally has the same response as a home-switch activation. During normal preset operation, either condition is treated as a fault and starts the stop/recovery behavior; the physical switches should not be reached during ordinary moves.
- Never use the Pi's 5 V pin for GPIO signals; Pi GPIOs are not 5 V tolerant.
- Timed movement is only an estimate. It is not a substitute for position feedback, physical stops, or independent emergency-stop protection.

## Configuration

Edit [`config/default.json`](config/default.json) before running:

- `arms.*.pwm_pin` and `arms.*.limit_pin` are BCM GPIO numbers and must all be unique. Current mapping: left PWM GPIO13 / limit GPIO27; right PWM GPIO19 / limit GPIO22. `gpiozero.Servo` generates the configured 50 Hz PWM pulse train on both output pins, so no additional GPIO hardware-PWM setting is needed.
- `home_active_level` selects the GPIO level that means the arm is at its limit; the current config uses active-LOW switches. The switch output reaching each Pi input must be 3.3 V-safe.
- `homing_reverse_pulse_us`, `rest_forward_pulse_us`, and `fault_release_pulse_us` are per-arm speed commands.
- `rest_duration_s` is the per-arm timed move from home to the straight-down rest position.
- Each preset provides a per-arm `pulse_us` speed command and `duration_s`. Tune these separately to synchronize the arms.
- The SPARK MAX factory deadband is centered around 1500 µs. Sample movement commands are deliberately outside that deadband; confirm the configured deadband and choose appropriate speeds for your mechanism.
- `sequence_interval_min_s` and `sequence_interval_max_s` select a random interval for each preset. The next preset starts only after both arms finish their current timed move and that interval has elapsed. Presets repeat in listed order.
- Homing and switch-release timeouts stop the motors and raise an error if a switch is not reached or released. A normal-operation switch activation stops both arms, waits `fault_pause_s`, moves only triggered arms forward until their switches release, and homes both arms again.

See the [Raspberry Pi GPIO wiring layout](docs/wiring.md) for physical header pin numbers and wiring notes.

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
sudo apt update
sudo apt install python3-venv python3-gpiozero python3-lgpio
python3 -m venv .venv --system-site-packages
. .venv/bin/activate
python -m pip install .
```

The virtual environment uses the OS GPIO Zero/lgpio packages for Raspberry Pi hardware access. Verify the imports before proceeding:

```sh
python -c "import gpiozero, lgpio; print('GPIO Zero and lgpio are available')"
```

Run the software tests first. They use mock hardware and do not move the arms:

```sh
python -m unittest discover -s tests -v
```

### Check limit-switch inputs without moving motors

This reads the two switch GPIOs only. At rest with the NC contacts closed, both should read `1`; pressing/opening a switch should make its input read `0` (home). A broken wire also reads `0`, by design.

```sh
python - <<'PY'
from time import sleep
from gpiozero import DigitalInputDevice

left = DigitalInputDevice(27, pull_up=False)
right = DigitalInputDevice(22, pull_up=False)
try:
    while True:
        print(f"left GPIO27={left.value}  right GPIO22={right.value}  ", end="\r", flush=True)
        sleep(0.1)
except KeyboardInterrupt:
    print()
finally:
    left.close()
    right.close()
PY
```

Confirm each switch changes independently and returns HIGH when released before testing motor movement.

### First live motor test

The controller does not have a motor-test mode. Starting it immediately commands **both arms to home**, then moves them forward to rest and starts cycling the presets. The sample PWM values and durations in `config/default.json` are not calibrated for your mechanism.

- Keep the mechanism supported, unobstructed, and clear of people. Have an accessible way to remove motor power immediately; Ctrl-C is not an emergency stop.
- With motor power off, verify wiring, switch readings, and that both arms can move freely. For the first powered test, use conservative pulse values and short travel times in a separate config file, and test under direct supervision.
- Check that each arm moves in the expected direction during homing and that activating its limit input causes the intended stop/recovery behavior. If direction or switch response is wrong, remove motor power immediately and correct wiring/configuration before retrying.
- Run manually first (do not enable the systemd service yet):

```sh
python -m lightupthenight --config config/default.json
```

Press Ctrl-C to stop; the controller commands neutral before closing GPIO resources. Use the independent motor-power disconnect if anything behaves unexpectedly.

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
