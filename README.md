# Light Up The Night

A Python controller for two SPARK MAX motor controllers connected to Raspberry Pi GPIO. It sends servo-style PWM pulses using the Linux kernel PWM interface and estimates arm travel from elapsed time; there are no position sensors other than the two home limit switches.

## Hardware and safety

- Each SPARK MAX must be configured to accept its factory-default PWM control range: 1000 Âµs full reverse, 1500 Âµs neutral, and 2000 Âµs full forward. Confirm the controller's PWM and signal-voltage requirements against its documentation before wiring.
- The sample pin assignments and motion values are placeholders. Validate the wiring and tune pulse widths and durations with the mechanism safely supported and clear of people and obstructions. A pulse away from neutral commands motor motion.
- Do not power motors from the Raspberry Pi. Use suitable motor power, a common signal ground where required, and electrical protection appropriate to the mechanism.
- The limit switches connect the Pi's 3.3 V (physical pin 17) through their normally-closed contacts to the GPIO inputs. The active-LOW setup uses internal pull-downs: the input is HIGH while the contact is closed and LOW when the switch opens. A broken wire also reads LOW and intentionally has the same response as a home-switch activation. During normal preset operation, either condition is treated as a fault and starts the stop/recovery behavior; the physical switches should not be reached during ordinary moves.
- Never use the Pi's 5 V pin for GPIO signals; Pi GPIOs are not 5 V tolerant.
- Timed movement is only an estimate. It is not a substitute for position feedback, physical stops, or independent emergency-stop protection.
- Kernel PWM continues sending the last pulse if the process crashes or is forcibly killed. Graceful shutdown sends neutral first, but software cannot guarantee neutral after an abrupt failure; keep an independent way to remove motor power immediately.

## Configuration

Edit [`config/default.json`](config/default.json) before running:

- `arms.*.pwm_pin` and `arms.*.limit_pin` are BCM GPIO numbers and must all be unique. Current mapping: left PWM GPIO18 / limit GPIO27; right PWM GPIO19 / limit GPIO22. `pwm_channel` selects the matching kernel PWM channel (0 for GPIO18, 1 for GPIO19); `motion.pwm_chip` selects the sysfs chip (0 on the verified Pi).
- `home_active_level` selects the GPIO level that means the arm is at its limit; the current config uses active-LOW switches. The switch output reaching each Pi input must be 3.3 V-safe.
- `motion.speed_offsets_us` defines the `slow`, `medium`, and `fast` speed levels as pulse-width offsets from neutral, in microseconds. The sample defaults are 35, 60, and 90 Âµs; lower offsets produce slower motion. On the tested SPARK MAX controllers 35 Âµs moves the arms; 5 Âµs is likely inside the factory deadband. The move to rest and fault recovery use `slow`; homing uses `homing_offset_us` if set.
- `motion.homing_offset_us` (optional) is the pulse offset used only while driving toward the home switch, so homing can be slower than the `slow` level. Omit it to home at the `slow` offset. The sample config leaves it unset, so homing uses the 35 µs `slow` offset. On the tested controllers 35 µs moves the arms while 18 µs and 28 µs did not (inside the deadband), so any value you set must stay above the SPARK MAX deadband; if the arm does not move, homing times out and you should raise it.
- `motion.right_arm_speed_adjustment_us` adjusts the right arm's offset at every speed level. Positive values increase its speed; negative values reduce it. The adjustment cannot reverse direction or exceed the configured pulse range.
- `motion.invert_direction` reverses the motor command direction globally while leaving neutral unchanged. Set it to `true` if the motors must run in reverse to move the arms in their configured forward direction. This applies to preset movement, homing, rest, and fault recovery.
- `rest_duration_s` is the per-arm timed move from home to the straight-down rest position.
- Each preset names its speed (`slow`, `medium`, or `fast`), then gives each arm a `direction` (`forward` or `reverse`) and `duration_s`. Both sample presets use `slow`; choose a speed for each new preset. Tune durations separately to synchronize the arms.
- The SPARK MAX factory deadband is centered around 1500 Âµs. Offsets that fall within that deadband produce no motion; confirm the configured deadband and adjust the offsets for your mechanism.
- Presets and sequence intervals are configured as described above, but they never start automatically. Without a `gait` section the controller parks at rest after homing; with one, it runs the walking gait.
- `gait` (optional) enables the walking-gait loop described in [Walking gait](#walking-gait).
- Homing and switch-release timeouts stop the motors and raise an error if a switch is not reached or released. A normal-operation switch activation stops both arms, waits `fault_pause_s`, moves only triggered arms forward until their switches release, and homes both arms again.

See the [Raspberry Pi GPIO wiring layout](docs/wiring.md) for physical header pin numbers and wiring notes.

The sample values are illustrative only; confirm actual speed, direction, and run time on the mechanism before unattended operation.

## Walking gait

When `config/default.json` has a `gait` section, the controller runs a perpetual walking-gait loop once homing and the move to rest finish. Without it, the controller parks at rest.

- **Home is the rear extreme of the arm swing.** The limit switch marks the back of the swing. **Rest (arm straight down) is the middle of the swing**, reached by the timed `rest_duration_s` move forward from home.
- **The arms are always opposite.** From rest, the left arm swings forward and the right arm swings back for a half swing out to the extremes. After that each full swing reverses both arms, so when one arm is at the front extreme the other is at the rear.
- **Slow speed only.** The gait always uses the `slow` speed level (`motion.speed_offsets_us.slow`).
- **Re-homing cancels drift.** Timing is open loop, so after `gait.rehome_every_cycles` full cycles the controller re-homes both arms, moves back to rest, and resumes the gait. Set it to 0 to disable.
- **Faults:** a limit-switch trip during the gait stops both arms and uses the normal fault recovery (pause, back off, re-home), then the gait restarts from rest.

| Setting | Meaning |
| --- | --- |
| `gait.swing_duration_s` | Time for one full rear-to-front swing at slow speed. The first leg after rest is half of it. |
| `gait.turnaround_pause_s` | Time both arms hold at neutral at each end of a swing (0 for none). |
| `gait.rehome_every_cycles` | Full cycles between re-homes (0 disables). |

Tune `swing_duration_s` on the mechanism, starting small. The rear extreme must stop short of the home switch, so the half swing from rest must be shorter than the rest travel. Compare against `rest_duration_s` at the same slow speed. Increase the duration gradually while watching the arms. The sample 0.6 s swing (about a quarter turn at slow speed, with re-homing every 10 cycles) was chosen from a first hardware run at 1.0 s, where the rear extreme stayed clear of the switch but drifted away from it over 10 cycles; it is not a calibrated value.

## Python versions

The project requires Python 3.13, which is the default `python3` version provided by Raspberry Pi OS Trixie. CI is configured to test Python 3.13, 3.14, and 3.15.

To confirm the interpreter on the Pi:

```sh
python3 --version
```

## Run on a Raspberry Pi

Use Raspberry Pi OS Trixie's default Python 3.13. Install GPIO Zero for the limit switches:

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

The controller does not have a motor-test mode. Starting it immediately commands **both arms to home**, then moves them forward to rest. With no `gait` section it then holds both at neutral; with the default `gait` section it immediately starts the perpetual walking gait (see [Walking gait](#walking-gait)). Presets never start automatically. The sample PWM values and durations in `config/default.json` are not calibrated for your mechanism.

- Keep the mechanism supported, unobstructed, and clear of people. Have an accessible way to remove motor power immediately; Ctrl-C is not an emergency stop.
- With motor power off, verify wiring, switch readings, and that both arms can move freely. For the first powered test, use conservative pulse values and short travel times in a separate config file, and test under direct supervision.
- Check that each arm moves in the expected direction during homing and that activating its limit input causes the intended stop/recovery behavior. If direction or switch response is wrong, remove motor power immediately and correct wiring/configuration before retrying.
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

The service runs the controller on every boot: it **homes both arms, moves them to rest, and then runs the walking gait forever**. It uses the `gait` section of `config/default.json`. **Once enabled, the arms move on their own at every power-up**, so keep people and obstructions clear and keep an independent way to cut motor power.

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
- **Faults are retried, a few times.** A fault that exits the process (for example a homing timeout because an arm is jammed or a switch is broken) restarts the service after 10 s, which homes again. After 5 failures in 10 minutes systemd stops retrying and leaves the service failed, so inspect the mechanism, then run `sudo systemctl reset-failed lightupthenight.service` and start it again.
- **Switch trips during the gait** are handled inside the controller (stop, back off, re-home, resume) and are not failures.
- **Boot order:** the service starts early in boot. If the arms' motor power comes on later than the Pi, the first homing may time out and the service will retry.

## Tests

Run the hardware-independent controller and config tests (including the gait and speed-level tests) with:

```sh
python3 -m unittest discover -s tests -v
```
