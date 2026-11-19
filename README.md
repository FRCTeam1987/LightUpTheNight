# Light Up The Night

A Python controller for two SPARK MAX motor controllers connected to Raspberry Pi GPIO. It sends servo-style PWM pulses using the Linux kernel PWM interface and estimates arm travel from elapsed time. The gait controller does not use position sensors or limit switches.

## Hardware and safety

- Each SPARK MAX must be configured to accept its factory-default PWM control range: 1000 µs full reverse, 1500 µs neutral, and 2000 µs full forward. Confirm the controller's PWM and signal-voltage requirements against its documentation before wiring.
- The sample pin assignments and motion values are placeholders. Validate the wiring and tune pulse widths and durations with the mechanism safely supported and clear of people and obstructions. A pulse away from neutral commands motor motion.
- Do not power motors from the Raspberry Pi. Use suitable motor power, a common signal ground where required, and electrical protection appropriate to the mechanism.
- The configured limit switches are retained for diagnostic scripts, but the gait controller ignores them. Natural swinging may activate them without stopping the gait. Do not rely on these switches for over-travel protection.
- **The tuned values are for the current bare test mechanism.** The speed offsets and gait's `swing_duration_s` were tuned without the real arms or their weight. Re-tune them on the loaded mechanism: weight and gravity affect travel and swing timing. Supervise powered tests and keep an independent way to cut motor power available.
- Never use the Pi's 5 V pin for GPIO signals; Pi GPIOs are not 5 V tolerant.
- Timed movement is only an estimate. It is not a substitute for position feedback, physical stops, or independent emergency-stop protection.
- Kernel PWM continues sending the last pulse if the process crashes or is forcibly killed. Graceful shutdown sends neutral first, but software cannot guarantee neutral after an abrupt failure; keep an independent way to remove motor power immediately.

## Configuration

Edit [`config/default.json`](config/default.json) before running:

- `arms.*.pwm_pin` and `arms.*.limit_pin` are BCM GPIO numbers and must all be unique. Current mapping: left PWM GPIO18 / limit GPIO27; right PWM GPIO19 / limit GPIO22. `pwm_channel` selects the matching kernel PWM channel (0 for GPIO18, 1 for GPIO19); `motion.pwm_chip` selects the sysfs chip (0 on the verified Pi).
- The configured limit inputs are not read by the gait controller; diagnostic scripts may still use them.
- `motion.speed_offsets_us` defines the `slow`, `medium`, and `fast` speed levels as pulse-width offsets from neutral, in microseconds. The current defaults are 45, 60, and 90 µs; lower offsets produce slower motion. On the tested SPARK MAX controllers 35 µs moves the arms; 5 µs is likely inside the factory deadband. The gait uses `slow`.
- `motion.right_arm_speed_adjustment_us` adjusts the right arm's offset at every speed level. Positive values increase its speed; negative values reduce it. The adjustment cannot reverse direction or exceed the configured pulse range.
- `motion.invert_direction` reverses the motor command direction globally while leaving neutral unchanged. Set it to `true` if the motors must run in reverse to move the arms in their configured forward direction.
- Each preset names its speed (`slow`, `medium`, or `fast`), then gives each arm a `direction` (`forward` or `reverse`) and `duration_s`. Both sample presets use `slow`; choose a speed for each new preset. Tune durations separately to synchronize the arms.
- The SPARK MAX factory deadband is centered around 1500 µs. Offsets that fall within that deadband produce no motion; confirm the configured deadband and adjust the offsets for your mechanism.
- Presets and sequence intervals are retained for configuration compatibility but do not start automatically. With a `gait` section, the controller starts the walking gait immediately; without one, it leaves both motors neutral.
- `gait` (optional) enables the walking-gait loop described in [Walking gait](#walking-gait).
- `gait.active_duration_s` is how long the gait runs before both motors are commanded neutral. `gait.pause_duration_s` is how long it remains neutral before the gait restarts.

See the [Raspberry Pi GPIO wiring layout](docs/wiring.md) for physical header pin numbers and wiring notes.

The sample values are illustrative only; confirm actual speed, direction, and run time on the mechanism before unattended operation.

## Walking gait

When `config/default.json` has a `gait` section, the controller starts the walking-gait loop immediately. It runs for `gait.active_duration_s`, commands both motors neutral for `gait.pause_duration_s`, then restarts the gait. The sample timing is 30 seconds on and 60 seconds off. Without a gait section, the controller leaves both motors neutral.

- **Startup swing:** both arms first move in the B direction at medium speed for half of `swing_duration_s`, moving them away from the low point. The A direction then swings them back across each other.
- **Ramped direction phases:** A runs slow for 0.5 seconds, medium for 0.5 seconds, then fast for 0.5 seconds. B repeats the same speed ramp in the opposite direction. Both arms move in opposite directions throughout.
- **Limit switches are ignored.** Activating a switch does not stop or change the gait. The arms swing under their own weight while the motors are neutral during the off interval.

| Setting | Meaning |
| --- | --- |
| `gait.swing_duration_s` | Sets the startup B-direction segment length to half this value. |
| `gait.turnaround_pause_s` | Time both arms hold at neutral between direction phases (0 for none). |
| `gait.active_duration_s` | Time the gait runs before both motors are commanded neutral. |
| `gait.pause_duration_s` | Time both motors remain neutral before the gait restarts. |

Tune the speed offsets and startup `swing_duration_s` on the mechanism. Since the limit switches are ignored by the gait controller, make sure the physical mechanism can safely tolerate the full swing and provide independent over-travel protection. Retune whenever the arms or their load change (see [Hardware and safety](#hardware-and-safety)).

## Python versions

The project requires Python 3.13, which is the default `python3` version provided by Raspberry Pi OS Trixie. CI is configured to test Python 3.13, 3.14, and 3.15.

To confirm the interpreter on the Pi:

```sh
python3 --version
```

## Run on a Raspberry Pi

Use Raspberry Pi OS Trixie's default Python 3.13. Install GPIO Zero for the diagnostic switch tools:

```sh
sudo apt update
sudo apt install python3-gpiozero python3-lgpio
```

The project can run directly from its source checkout; no build or package install is needed for local edits to take effect. Verify the GPIO Zero import:

```sh
python -c "import gpiozero, lgpio; print('GPIO Zero and lgpio are available')"
```

Enable the kernel PWM overlay in `/boot/firmware/config.txt`, then reboot:

```ini
[all]
dtoverlay=pwm-2chan
```

Verify that `/sys/class/pwm/pwmchip0/npwm` reports `2` and GPIO18/GPIO19 are in PWM alternate mode before running the application. Kernel PWM sysfs export and control usually require root or explicit sysfs permissions.

Run the software tests first. They use mock hardware and do not move the arms:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
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

The controller does not have a motor-test mode. Starting it immediately begins the walking gait (see [Walking gait](#walking-gait)), without homing or checking the limit switches. Without a `gait` section, both motors remain neutral. Presets never start automatically. The sample PWM values and durations in `config/default.json` are not calibrated for your mechanism.

- Keep the mechanism supported, unobstructed, and clear of people. Have an accessible way to remove motor power immediately; Ctrl-C is not an emergency stop.
- With motor power off, verify wiring and that both arms can move freely. For the first powered test, use conservative pulse values and short travel times in a separate config file, and test under direct supervision.
- Check that each arm moves in the expected direction. Limit-switch inputs do not stop the gait; use suitable physical stops and an independent way to cut motor power.
- Run manually first (do not enable the systemd service yet):

```sh
sudo env PYTHONPATH=src python3 -m lightupthenight --config config/default.json
```

Press Ctrl-C to stop; the controller commands neutral before closing GPIO resources. Use the independent motor-power disconnect if anything behaves unexpectedly.

### Check the speed levels

`scripts/speed_check.py` drives both arms forward and then in reverse at each of `slow`, `medium`, and `fast`, and reads each PWM channel's `duty_cycle` back from sysfs to confirm the commanded pulse width is really being output. Each arm reacts only to its own home switch: an arm driving toward home stops when its own switch trips while the other keeps going, and a tripped switch never blocks a forward move (which leaves the switch). Ctrl-C stops both arms. Start with the arms near rest and clear of obstructions:

```sh
sudo env PYTHONPATH=src python3 scripts/speed_check.py --config config/default.json
```

It ends with `PASS: all pulses matched` when every pulse was as expected. It checks the output, not the motion, so also confirm by eye that each speed is faster than the last and that forward and reverse go in opposite directions.

## Start at boot with systemd

The service runs the controller on every boot and starts the walking gait immediately. It uses the `gait` section of `config/default.json`, alternating 30 seconds of gait and 60 seconds neutral. **Once enabled, the arms move on their own at every power-up**, so keep people and obstructions clear and keep an independent way to cut motor power.

The unit runs as root (kernel PWM sysfs needs it) from the checkout at `/home/broncobots/LightUpTheNight`, with config `config/default.json` from that checkout. Edit `deploy/lightupthenight.service` if your user or paths differ.

1. Install the Raspberry Pi OS `python3-gpiozero` and `python3-lgpio` packages and enable the `pwm-2chan` overlay as above, then confirm the manual run works first.
2. Install and start the service:

   ```sh
   sudo install -m 0644 deploy/lightupthenight.service /etc/systemd/system/lightupthenight.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now lightupthenight.service
   ```

Check status and logs with `systemctl status lightupthenight.service` and `journalctl -u lightupthenight.service -f`. After changing the code or `config/default.json`, copy the files over and run `sudo systemctl restart lightupthenight.service`. To stop it, run `sudo systemctl stop lightupthenight.service`; to keep it from starting at boot, run `sudo systemctl disable lightupthenight.service`.

Behavior to know about:

- **Clean stop:** `systemctl stop` sends SIGTERM, which the controller handles like Ctrl-C: it commands neutral before closing. A crash or `kill -9` cannot do that, and kernel PWM keeps sending its last pulse, so the unit releases the PWM channels before each start.
- **Switch trips during the gait** are ignored by the controller. Make sure physical stops and independent motor-power disconnects are suitable for the mechanism.
- **Boot order:** the service starts early in boot. Ensure the motor controllers are ready before the gait starts.

## Tests

Run the hardware-independent controller and config tests (including the gait and speed-level tests) with:

```sh
python3 -m unittest discover -s tests -v
```
