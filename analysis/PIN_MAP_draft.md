# RealTime CNC "GSD RTS-1" (RTS-1 Open-Loop) — pin map (firmware-extracted draft)

## Official specs (realtimecnc.com/product_specs) — cross-validated
- 5 drivers: X, Y1, Y2, Z, A — **matches 5 STEP pins found**. DRV8452, 2.8A RMS/ch, 5–48V, microstep up to 1/64.
- Spindle: **RS-485 / Modbus VFD** (dedicated connector) + On/Off via an output — **confirms USART1 Modbus hypothesis**. (Not primarily 0–10V analog.)
- DB-25 "I/O": **8 isolated normally-open inputs + 4 isolated outputs (50V/100mA)**.
- Probe + Tool Setter: separate **dedicated** connectors (extra inputs beyond the DB25 8).
- E-Stop: on the **motor power supply** side (may not be an MCU GPIO).
- USB 2.0 USB-C (CDC). Power: 6-pin Molex Mini-Fit Jr. "Custom RTOS" (= FreeRTOS firmware we dumped).

Source: static analysis of `stock_RTS-1_backup.bin` (STM32F401RCT6).
Method: function-segmented Thumb-2 disassembly; recovered HAL_GPIO_WritePin /
ReadPin call sites (port in r0, pin mask immediate in r1) + direct BSRR writes.

Confidence: **H** = strong (clear grouping + matches CNC topology), **M** = inferred,
**L** = needs verification.

## Motion — stepper signals
| Signal | Pin(s) | How found | Conf |
|---|---|---|---|
| **STEP ×4–5** | **PB0, PB2, PB8, PB10, PB13** | direct BSRR writes (fast toggling, all on one port = coordinated step) | H (that these are step pulses) / M (which is which axis) |
| **DIR ×4** | **PC1, PC2, PC3, PC4** | HAL_GPIO_WritePin, 4 consecutive outputs | H |
| **Motor ENABLE** | TBD (PA8 reassigned to RS-485 DE) | DRV8452 nSLEEP/EN — pin not yet isolated; may be a single shared GPIO or tied | L |

4 axes = X / Y1 / Y2 / Z. The 5th BSRR pin (PB13) may be a 5th step, a shared
pulse, or a DIR — needs disambiguation.

## Inputs — limits / probe / toolsetter / e-stop
| Signal | Pins | How found | Conf |
|---|---|---|---|
| Digital inputs (≈7) | **PA5, PA6, PA7, PC5, PC6, PC7, PC14** | HAL_GPIO_ReadPin | H (that they're inputs) / L (role mapping) |

7 inputs fits 4× limit/home + PROBE + TOOLSETTER + E-STOP. Exact assignment TBD.

## Spindle / VFD
| Signal | Pin | Notes | Conf |
|---|---|---|---|
| **Modbus/RS485 (VFD)** | **USART1: PA9=TX, PA10=RX; DE/RE=PA8** | Transceiver = **ISL3485** (U5, 8-SOIC, confirmed by photo). DI←PA9, RO→PA10, DE+/RE←**PA8** (PA8 found as WritePin inside the USART-touching TX function; adjacent to USART1 pins). | H |
| **Spindle PWM (0–10V)** | a TIM channel (TIM1 heavily used) — exact pin TBD | "PWM" connector; `spindle_mode` setting selects PWM vs VFD | L |
| USART6 | barely referenced (1×) — possibly pendant/unused | | L |

## Other peripherals seen (block level — confirmed from base-address refs)
- **SPI1** — likely settings EEPROM or an SPI DAC for clean 0–10V spindle. (M)
- **I2C1** — EEPROM / display / IO-expander. (L)
- **ADC1** (+ DMA2) — analog sensing (spindle load? aux input). (L)
- **USB_OTG_FS** — host CDC link (PA11/PA12). (H)
- Timers in use: TIM1,2,3,4,5,9,10,11.

## Ambiguous / artifacts
- PA15 / PB15 / PC15 appeared in BOTH read and write lists — likely decode noise;
  could be spindle-enable / relay / status LED. Verify physically.

## To finish the map (before flashing grblHAL)
1. Disambiguate STEP↔axis and the 7 inputs — deeper RE (Ghidra w/ symbols) or
   multimeter from each DRV8452 STEP/DIR pin back to the MCU.
2. Confirm spindle path: is there an RS485 transceiver (Modbus) and/or an op-amp
   on the PWM line (0–10V)? Photo of the VFD/PWM area decides it.
3. Confirm motor ENABLE polarity and the e-stop input.
