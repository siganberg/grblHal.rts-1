/*
  rts1_map.h - grblHAL board map for the RealTime CNC RTS-1 (Onefinity) controller

  MCU: STM32F401RCT6 | 5x TI DRV8452 (STEP/DIR) | RS-485 Modbus VFD (ISL3485) | USB-C CDC

  Pin map reverse-engineered from the stock firmware (see ../../../PIN_MAP.md).
  Motion + spindle pins are high confidence. Items marked PROVISIONAL (driver<->axis
  order, input role mapping) must be confirmed at bring-up (jog an axis / toggle a pin).

  Part of grblHAL. GPLv3 (see COPYING).
*/

#if N_ABC_MOTORS > 2
#error "RTS-1 supports at most 2 extra motors (A axis + ganged Y2)."
#endif

#define BOARD_NAME "RealTime CNC RTS-1"
#define BOARD_URL  "https://realtimecnc.com"
#define HAS_BOARD_INIT          // board_init() in boards/rts1.c asserts fans + power enable at boot

// ============================ Stepper motion ============================
// Driver order: 0=X 1=Y 2=Y2(ganged) 3=Z 4=A
// STEP + DIR are BOTH on GPIOB (verified by firmware RE). The DRV8452s run in
// SPI mode: there is NO GPIO stepper-enable -- outputs are enabled over SPI
// (CTRL1 EN_OUT bit) and current is set via SPI (CTRL11 TRQ_DAC) in board_init().
// The 5 SPI chip-selects are PC0..PC4 (board-managed in rts1.c) -- these were
// previously (wrongly) mapped as the DIR pins. SPI1 = PA5/PA6/PA7.

#define STEP_PORT               GPIOB
#define X_STEP_PIN              0
#define Y_STEP_PIN              2
#define Z_STEP_PIN              10
#define STEP_OUTMODE            GPIO_BITBAND

#define DIRECTION_PORT          GPIOB       // DIR on GPIOB (PB1/5/9/12/14), not GPIOC
#define X_DIRECTION_PIN         1
#define Y_DIRECTION_PIN         5
#define Z_DIRECTION_PIN         12
#define DIRECTION_OUTMODE       GPIO_BITBAND

// No *_ENABLE_PIN: DRV8452 output-enable is over SPI (EN_OUT), see board_init().

// ---- A axis = motor M3 (driver 4) ----
#if N_ABC_MOTORS > 0
#define M3_AVAILABLE
#define M3_STEP_PORT            GPIOB
#define M3_STEP_PIN             13
#define M3_DIRECTION_PORT       GPIOB
#define M3_DIRECTION_PIN        14
#endif

// ---- Ganged Y2 = motor M4 (driver 2), for Y auto-squaring ----
#if N_ABC_MOTORS > 1
#define M4_AVAILABLE
#define M4_STEP_PORT            GPIOB
#define M4_STEP_PIN             8
#define M4_DIRECTION_PORT       GPIOB
#define M4_DIRECTION_PIN        9
#endif

// ============================ Limit inputs (PROVISIONAL) ============================
#define X_LIMIT_PORT            GPIOC
#define X_LIMIT_PIN             5
#define Y_LIMIT_PORT            GPIOC
#define Y_LIMIT_PIN             6
#define Z_LIMIT_PORT            GPIOC
#define Z_LIMIT_PIN             7
#define LIMIT_INMODE            GPIO_BITBAND

#if N_ABC_MOTORS > 1
#define M4_LIMIT_PORT           GPIOB   // Y2 home switch (auto-square)
#define M4_LIMIT_PIN            4
#endif

// ============================ Spindle ============================
// RS-485 Modbus VFD on USART1 (PA9 TX / PA10 RX), ISL3485 DE on PA8.
// Also a hardware PWM on PA0 (TIM5_CH1) for PWM/laser spindle mode.

// Modbus VFD: console is USB-CDC, so the (only) hardware UART slot = USART1 for Modbus.
#define SERIAL_PORT             1       // USART1 PA9/PA10 -> Modbus/RS-485 (ISL3485)

#define AUXOUTPUT0_PORT         GPIOA   // Spindle PWM (TIM5_CH1)
#define AUXOUTPUT0_PIN          0
#define AUXOUTPUT1_PORT         GPIOA   // RS-485 DE/RE (ISL3485) -> Modbus direction
#define AUXOUTPUT1_PIN          8

// RS-485 direction (DE) pin for the Modbus plugin = aux output 1 (PA8).
#define MODBUS_DIR_AUX          1

// NOTE: PA15, PB15, PC15 are NOT grbl-managed here. board_init() (boards/rts1.c)
// drives them HIGH at boot = 2 cooling fans + master logic enable (stock power-on).

// NOTE: no SPINDLE_PWM here on purpose - PA0's PWM timers (TIM5/TIM2) are used by
// grblHAL for step/RPM timing, so a PA0 PWM spindle hangs boot. We use a plain
// on/off spindle instead (DRIVER_SPINDLE_ENABLE = SPINDLE_ENA, no timer).
#if DRIVER_SPINDLE_ENABLE & SPINDLE_PWM
#define SPINDLE_PWM_PORT        AUXOUTPUT0_PORT
#define SPINDLE_PWM_PIN         AUXOUTPUT0_PIN
#endif

// Spindle on/off enable. Required for the on/off spindle to register (otherwise
// only Modbus VFDs are selectable -> nuisance timeouts with nothing connected).
// PB11 is a PLACEHOLDER (unused pin); the real stock spindle on/off line gets
// wired up when a spindle is actually connected.
#if DRIVER_SPINDLE_ENABLE & SPINDLE_ENA
#define SPINDLE_ENABLE_PORT     GPIOB
#define SPINDLE_ENABLE_PIN      11
#endif

// ============================ Control + probe inputs (PROVISIONAL) ============================
// NOTE: PB15 is a cooling fan driven by board_init() (active-low), NOT an input.
// The tool-setter / second probe needs a different free pin (TBD at bring-up).
#define AUXINPUT0_PORT          GPIOC   // Reset / E-stop
#define AUXINPUT0_PIN           13
#define AUXINPUT1_PORT          GPIOC   // Probe
#define AUXINPUT1_PIN           14

#if CONTROL_ENABLE & CONTROL_HALT
#define RESET_PORT              AUXINPUT0_PORT
#define RESET_PIN               AUXINPUT0_PIN
#endif

#if PROBE_ENABLE
#define PROBE_PORT              AUXINPUT1_PORT
#define PROBE_PIN               AUXINPUT1_PIN
#endif

/* EOF */
