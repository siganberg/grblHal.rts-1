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
| **I2C1** | PB6=SCL, PB7=SDA (AF4, open-drain) → **EEPROM + TCA9555 I/O expander** | H |
| **SPI1** (DRV8452 ×5) | PA5=SCK, PA6=MISO, PA7=MOSI (AF5); CS = PC0–PC4 | H |
| Analog (ADC1) | PA1, PA4 (VM sense; unused by our fw) | M |

## Isolated DB-25 I/O — via TCA9555 I2C expander (CONFIRMED at bring-up)
**The 8 isolated inputs, PROBE, tool-setter, and 4 outputs are NOT direct MCU pins.**
They are opto-isolated (PC817 input optos, CPC1017N output SSRs `U24/U7/U8/U9`) and
gathered on a **TCA9555 16-bit I2C I/O expander = U6** (marked `PW555`), on **I2C1
(PB6/PB7)** at 7-bit address **0x27** (HAL 8-bit 0x4E/0x4F). Stock's `SysInputTask`
reads it via `HAL_I2C_Master_Transmit(0x4E, reg=0x00, 1)` then `…_Receive(0x4E, buf, 2)`
= input ports 0+1 = 16 bits. **Active-LOW** (grounding an input to IGND → bit = 0).

Expander bit map (found with `$IEX` while shorting each connector):
| Bit | Signal | |
|---|---|---|
| 0–7 | 8 isolated inputs (DB-25 pins 1–8) | idle high |
| **8** | **PROBE** (DB-25 pin 22 / connector **J6**) | active-low |
| **9** | **tool-setter / TLS** | active-low |
| 11–14 | the 4 isolated OUTPUTS (OUT0–3, CPC1017N) | |

grblHAL integration (`boards/rts1.c`): `rts1_realtime` polls the expander ~500 Hz over
I2C and caches it (`rts1_iso`); `hal.probe.get_state` is overridden to read the cache
(ISR-safe — never touches I2C from the probe ISR path). PROBE + TLS are **tied**
(bit 8 OR bit 9 → probe trigger) because grblHAL has no separate toolsetter letter in
the status report — see `RTS1_PROBE_TIE_TLS`. Diagnostic: **`$IEX`** dumps the 16 bits.

## Extra outputs / straps (CONFIRMED at bring-up)
**PA15** = master enable (active-LOW: rail + fans). **PB15** = driver strap (hold HIGH;
toggling audibly disrupts steppers). **PC15** = DRV8452 nSLEEP/reset. **PC14** = SPI
interface strap (LOW = SPI mode). **PC13** = reset / e-stop input. **PC5** = OR-tied
DRV8452 nFAULT. Status-LED pin is timer-driven (not a software GPIO) — unidentified,
deprioritized.

## Corrections vs the original recovered map (above)
- DIR is **PB1/5/9/12/14**, not PC0–4 (PC0–4 are the SPI **CS** lines). STEP = PB0/2/8/10/13.
- DRV8452 output-enable is over **SPI (EN_OUT)** — there is no GPIO enable line.
- PA5/6/7 are **SPI1** (to the drivers), not spare inputs.
- The "9 direct-GPIO inputs" guess was WRONG — user inputs are all behind the TCA9555.

## Open items
1. Map the remaining expander bits: the 8 isolated inputs (bits 0–7) and 4 outputs (11–14).
2. Status-LED pin (timer-driven, low priority).

## Flashing (recap)
USB DFU via BOOT0 button, RDP0. `dfu-util -a 0 -s 0x08000000:leave -D grblHAL.bin`.
Restore stock: same with `firmware/RTS-1_fw_v1.4.7_original_2026-06-11.bin`.
