/*
  rts1.c - board init for the RealTime CNC RTS-1 (Onefinity) controller

  The stock firmware drives several outputs HIGH at boot to power the board up:
  the two cooling fans come on with USB power alone, and a master logic-enable
  is asserted. Reverse-engineering showed these on PB15, PC15 (driven HIGH at
  boot -> fans) and PA15 (gated by the e-stop sense on PC14 -> master enable).

  We replicate that here so grblHAL brings the board to the same powered state.
  (Motor supply VM+ is fed directly via the power connector and gated by the
  external e-stop, so it is not switched by the MCU.)

  Part of grblHAL. GPLv3 (see COPYING).
*/

#include "driver.h"

#if defined(BOARD_RTS1)

void board_init (void)
{
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();

    GPIO_InitTypeDef gpio = {
        .Mode  = GPIO_MODE_OUTPUT_PP,
        .Pull  = GPIO_NOPULL,
        .Speed = GPIO_SPEED_FREQ_LOW
    };

    // PB15, PC15 = cooling fans (on at boot, like stock).
    // PA15       = master logic enable (asserted when e-stop released).
    gpio.Pin = GPIO_PIN_15;
    HAL_GPIO_Init(GPIOA, &gpio);
    HAL_GPIO_Init(GPIOB, &gpio);
    HAL_GPIO_Init(GPIOC, &gpio);

    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_15, GPIO_PIN_SET);   // master enable
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_15, GPIO_PIN_SET);   // fan 1
    HAL_GPIO_WritePin(GPIOC, GPIO_PIN_15, GPIO_PIN_SET);   // fan 2
}

#endif // BOARD_RTS1
