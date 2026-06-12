# RealTime CNC RTS-1 (Open-Loop) — STM32F401RCT6 pin map

Recovered from firmware `firmware/RTS-1_fw_v1.4.7_original_2026-06-11.bin` by capstone
disassembly: all 22 `HAL_GPIO_Init` call sites + the authoritative motion-init function
`0x08012C24` (final pin modes + initial states) + WritePin/ReadPin/BSRR + ISL3485 photo.
Confidence: **H** strong · **M** inferred · **L** verify.

Architecture: **5 drivers** (DRV8452) → **4 logical axes** via `assigned_axis[5]`
(dual-Y: Y1+Y2 ganged to one Y). Settings arrays are [4] = X,Y,Z,A.

## Motion (driver-indexed 0..4)
| Signal | Pins (driver 0→4) | Conf |
|---|---|---|
| **STEP ×5** | **PB0, PB2, PB8, PB10, PB13** (BSRR-toggled in `stepperTask`) | H |
| **DIR ×5** | **PC0, PC1, PC2, PC3, PC4** (init HIGH, vhigh speed) | H |
| **ENABLE/nSLEEP ×5** | **PB1, PB5, PB9, PB12, PB14** (init LOW = disabled) | M |

Driver→axis: default almost certainly X, Y1, Y2, Z, A (verify at bring-up by jogging).

## Spindle
| Signal | Pin | Conf |
|---|---|---|
| **Modbus VFD (RS-485)** | USART1 **PA9=TX, PA10=RX**, **DE/RE=PA8** (ISL3485 U5) | H |
| **Spindle/laser PWM** | **PA0** (AF2 TIM5_CH1; `pwm_freq`/`pwm_max` settings) | M |
| Spindle on/off output | one of PA15 / PB15 / PC15 | L |

## Other buses / analog
| Function | Pins | Conf |
|---|---|---|
| **USB CDC** | PA11, PA12 (AF10 OTG_FS) | H |
| **I2C1** (EEPROM/display) | PB6=SCL, PB7=SDA (AF4, open-drain) | M |
| Analog (ADC1) | PA1, PA4 | M |
| SPI1? (PA5/6/7 AF5) | **contradicted** — motion-init sets PA5/6/7 as INPUT | L |

## Inputs (digital, from motion-init final config)
**PA5, PA6, PA7, PB4, PC5, PC6, PC7, PC13, PC14** (9 inputs)
→ 8 isolated DB-25 inputs + probe + toolsetter (per spec; e-stop is on motor-power side).
Exact role-per-pin TBD. Conf: H as inputs, L on role mapping.

## Extra outputs (init input→output)
**PA15, PB15, PC15** = status-LED (blinks on boot) + spindle-on/off + 1 aux. Which is
which: TBD (L).

## Open items (resolve at bring-up — all cheap)
1. Driver→axis order (jog each, watch which motor moves).
2. Which of PA15/PB15/PC15 is the status LED vs spindle-relay.
3. Confirm PA5/6/7 are inputs vs SPI (multimeter / scope, or check for an SPI device).
4. ENABLE: is it 5 per-driver lines (PB1/5/9/12/14) or are some something else.

## Flashing (recap)
USB DFU via BOOT0 button, RDP0. `dfu-util -a 0 -s 0x08000000:leave -D grblHAL.bin`.
Restore stock: same with `firmware/RTS-1_fw_v1.4.7_original_2026-06-11.bin`.
