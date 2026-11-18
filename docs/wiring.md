# Raspberry Pi GPIO wiring layout

This layout uses the standard 40-pin Raspberry Pi header numbering. The physical header pins and BCM GPIO numbers are different: use the **BCM GPIO** values in `config/default.json`; use the **physical pin** values to locate pins on the header.

## Pin assignments

| Function | Physical header pin | BCM GPIO | Connect to |
| --- | ---: | ---: | --- |
| Left SPARK MAX PWM signal | 33 | GPIO13 | Left controller PWM signal wire |
| Right SPARK MAX PWM signal | 35 | GPIO19 | Right controller PWM signal wire |
| Left home limit input | 13 | GPIO27 | Left normally-closed switch output |
| Right home limit input | 15 | GPIO22 | Right normally-closed switch output |
| 3.3 V switch supply | 17 | 3V3 | Feed to the common contact side of both switches |
| PWM/signal ground | 39 | GND | Ground wires for both SPARK MAX PWM leads |

The matching application configuration is:

```text
left:  pwm_pin=13, limit_pin=27, home_active_level=LOW
right: pwm_pin=19, limit_pin=22, home_active_level=LOW
```

The application uses `gpiozero.Servo` with a 20 ms frame (50 Hz) and configurable 1000–2000 µs pulses. gpiozero requests PWM output on the configured GPIOs; there is no separate per-pin PWM enable setting in this project.

## Signal layout

```mermaid
flowchart LR
    subgraph Pi["Raspberry Pi 40-pin header"]
        P33["Pin 33 / GPIO13"]
        P35["Pin 35 / GPIO19"]
        P13["Pin 13 / GPIO27"]
        P15["Pin 15 / GPIO22"]
        P39["Pin 39 / GND"]
        P17["Pin 17 / 3.3 V"]
    end

    P33 -->|"PWM signal"| LeftPWM["Left SPARK MAX signal"]
    P35 -->|"PWM signal"| RightPWM["Right SPARK MAX signal"]
    P39 -->|"common signal ground"| LeftGND["Left SPARK MAX ground"]
    P39 -->|"common signal ground"| RightGND["Right SPARK MAX ground"]

    P17 --> LeftSwitch["Left NC limit switch"]
    P17 --> RightSwitch["Right NC limit switch"]
    LeftSwitch -->|"closed: 3.3 V / HIGH; opens at home"| P13
    RightSwitch -->|"closed: 3.3 V / HIGH; opens at home"| P15
    P13 -.->|"internal pull-down"| P39
    P15 -.->|"internal pull-down"| P39
```

## Wiring and safety notes

- Connect physical pin 17 (3.3 V) to one side of each normally-closed switch. Connect the other side of the left switch to physical pin 13 (GPIO27), and the other side of the right switch to physical pin 15 (GPIO22). Configure the switch so its NC contact opens when the arm reaches home. gpiozero enables an internal pull-down for the LOW-active input: closed switch reads HIGH; open-at-home reads LOW.
- Connect each Pi PWM GPIO to the corresponding SPARK MAX **signal** wire, and connect both PWM lead ground wires to physical pin 39.
- Verify the SPARK MAX accepts the Pi's 3.3 V PWM logic level and that its signal ground can be shared with the Pi before connecting. Do not connect a motor-power lead to a Pi GPIO or Pi ground.
- Physical pin 17 is a **3.3 V supply**, not a GPIO output. Never connect the Pi's 5 V supply to these GPIO inputs.
- With this normally-closed passthrough wiring, an open switch or broken wire both read LOW and intentionally have the same behavior. During startup homing, LOW is treated as already at home. During normal preset operation, LOW is an unexpected limit fault: both motors stop, the controller waits, backs off the indicated arm while the input releases, then re-homes. A persistent broken wire stays LOW, so recovery times out and stops rather than continuing motion.
- The arms should not normally contact their limit switches during preset movement; configure timed travel with clearance. The switches and wiring fault signal are intended as a fault response, not routine position control.
- Confirm the physical pin numbering against the exact Raspberry Pi board and header before applying power. The BCM assignments used here correspond to physical pins 13=GPIO27, 15=GPIO22, 17=3.3 V, 33=GPIO13, 35=GPIO19, and 39=GND on the standard 40-pin header.
- Test the wiring first with motor power disconnected. PWM pulses away from 1500 µs command motion once the SPARK MAX and motor are powered.
