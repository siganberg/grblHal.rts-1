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

// ============================ Stepper motion ============================
// Driver order (PROVISIONAL): 0=X 1=Y 2=Y2(ganged) 3=Z 4=A
// STEP all on GPIOB, DIR all on GPIOC, per-driver ENABLE on GPIOB.

#define STEP_PORT               GPIOB
#define X_STEP_PIN              0
#define Y_STEP_PIN              2
#define Z_STEP_PIN              10
#define STEP_OUTMODE            GPIO_BITBAND

#define DIRECTION_PORT          GPIOC
#define X_DIRECTION_PIN         0
#define Y_DIRECTION_PIN         1
#define Z_DIRECTION_PIN         3
#define DIRECTION_OUTMODE       GPIO_BITBAND

// Per-driver enable (DRV8452). Each axis its own enable line.
#define X_ENABLE_PORT           GPIOB
#define X_ENABLE_PIN            1
#define Y_ENABLE_PORT           GPIOB
#define Y_ENABLE_PIN            5
#define Z_ENABLE_PORT           GPIOB
#define Z_ENABLE_PIN            12

// ---- A axis = motor M3 (driver 4) ----
#if N_ABC_MOTORS > 0
#define M3_AVAILABLE
#define M3_STEP_PORT            GPIOB
#define M3_STEP_PIN             13
#define M3_DIRECTION_PORT       GPIOC
#define M3_DIRECTION_PIN        4
#define M3_ENABLE_PORT          GPIOB
#define M3_ENABLE_PIN           14
#endif

// ---- Ganged Y2 = motor M4 (driver 2), for Y auto-squaring ----
#if N_ABC_MOTORS > 1
#define M4_AVAILABLE
#define M4_STEP_PORT            GPIOB
#define M4_STEP_PIN             8
#define M4_DIRECTION_PORT       GPIOC
#define M4_DIRECTION_PIN        2
#define M4_ENABLE_PORT          GPIOB
#define M4_ENABLE_PIN           9
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
#define AUXOUTPUT1_PORT         GPIOC   // Spindle enable / on-off (PROVISIONAL)
#define AUXOUTPUT1_PIN          15
#define AUXOUTPUT2_PORT         GPIOA   // RS-485 DE/RE (ISL3485) -> Modbus direction
#define AUXOUTPUT2_PIN          8

// RS-485 direction (DE) pin for the Modbus plugin = aux output 2 (PA8).
// NOTE: verify the resolved aux index at bring-up (scope PA8 during a Modbus frame).
#define MODBUS_DIR_AUX          2

#if DRIVER_SPINDLE_ENABLE & SPINDLE_PWM
#define SPINDLE_PWM_PORT        AUXOUTPUT0_PORT
#define SPINDLE_PWM_PIN         AUXOUTPUT0_PIN
#endif
#if DRIVER_SPINDLE_ENABLE & SPINDLE_ENA
#define SPINDLE_ENABLE_PORT     AUXOUTPUT1_PORT
#define SPINDLE_ENABLE_PIN      AUXOUTPUT1_PIN
#endif

// ============================ Control + probe inputs (PROVISIONAL) ============================
#define AUXINPUT0_PORT          GPIOC   // Reset / E-stop
#define AUXINPUT0_PIN           13
#define AUXINPUT1_PORT          GPIOC   // Probe
#define AUXINPUT1_PIN           14
#define AUXINPUT2_PORT          GPIOB   // Tool setter (second probe)
#define AUXINPUT2_PIN           15

#if CONTROL_ENABLE & CONTROL_HALT
#define RESET_PORT              AUXINPUT0_PORT
#define RESET_PIN               AUXINPUT0_PIN
#endif

#if PROBE_ENABLE
#define PROBE_PORT              AUXINPUT1_PORT
#define PROBE_PIN               AUXINPUT1_PIN
#endif

#if PROBE2_ENABLE
#define PROBE2_PORT             AUXINPUT2_PORT
#define PROBE2_PIN              AUXINPUT2_PIN
#endif

/* EOF */
