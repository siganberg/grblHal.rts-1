/*
  rts1.c - board init for the RealTime CNC RTS-1 (Onefinity) controller

  Two things happen here at boot:

  1) MASTER ENABLE / fans. PA15 is the board master enable (active-LOW): driving
     it LOW powers the logic/driver rail that also feeds the two cooling fans
     (CONFIRMED on hardware - fans only run with PA15 low). PB15/PC15 are board
     power/enable straps, asserted HIGH (PC15 is most likely the global driver
     power gate). Motor supply VM+ is fed via the power connector and gated by
     the external e-stop, so it is not switched by the MCU.

  2) DRV8452 SPI configuration. The five DRV8452 stepper drivers are strapped
     into SPI interface mode (MODE strap; interface-select read on PC14, LOW =
     SPI). In SPI mode the outputs are Hi-Z until EN_OUT (CTRL1 bit7) is written
     1, and the current is zero until TRQ_DAC (CTRL11) is written - so grblHAL
     MUST send this config or the motors stay completely limp (they step but
     produce no torque). Sequence + SPI params reverse-engineered from stock fw:
       SPI1 master, mode 1 (CPOL=0/CPHA=1), 8-bit, MSB-first, /16, software NSS.
       SPI1 pins: PA5=SCK, PA6=MISO, PA7=MOSI (AF5).
       Chip-selects (one per driver, active-low): PC0..PC4.
       16-bit frame sent as 2 bytes: { (rw<<6)|addr6, data8 }, rw: write=0 read=1.
     Note: STEP (PB0/2/8/10/13) and DIR (PB1/5/9/12/14) stay as GPIO - stock
     leaves SPI_STEP/SPI_DIR = 0 so the driver follows the external STEP/DIR pins.

  Part of grblHAL. GPLv3 (see COPYING).
*/

#include "driver.h"

#if defined(BOARD_RTS1)

// ---- DRV8452 current settings (CTRL10/CTRL11 DAC codes, 0..255; 255 = full
// scale). Conservative bring-up defaults - raise toward 0xFF for more torque.
// Motors are rated 2.8 A RMS/driver; full scale corresponds to that. ----
#define RTS1_DRV_RUN_CURRENT   0xC0   // CTRL11 TRQ_DAC (move) ~75% (~2.1A)
#define RTS1_DRV_HOLD_CURRENT  0x60   // CTRL10 ISTSL  (idle) ~37% (cooler hold)
#define RTS1_DRV_MICROSTEP     0x07   // CTRL2 low nibble: 0x07 = 1/32 step (0x06=1/16)
                                      // higher microstep -> less resonance/noise.
                                      // NOTE: steps/mm ($100-103) must scale with this!

#define DRV_N        5
#define DRV_CS_MASK  (GPIO_PIN_0|GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3|GPIO_PIN_4)

// Short busy-delay for SPI CS setup/hold timing margin (~few us at 84 MHz).
static void drv_dly (void) { for(volatile int d = 0; d < 240; d++); }

// 8-bit full-duplex SPI1 transfer (direct register access; no HAL SPI module).
static uint8_t spi_xfer (uint8_t b)
{
    while(!(SPI1->SR & SPI_SR_TXE));
    *(volatile uint8_t *)&SPI1->DR = b;
    while(!(SPI1->SR & SPI_SR_RXNE));
    return *(volatile uint8_t *)&SPI1->DR;
}

static void drv_write (uint8_t i, uint8_t reg, uint8_t data)
{
    GPIOC->BSRR = (uint32_t)(1u << i) << 16;     // CS_i LOW
    drv_dly();                                   // CS setup
    spi_xfer((uint8_t)(reg & 0x3F));             // rw=0 (write)
    spi_xfer(data);
    while(SPI1->SR & SPI_SR_BSY);
    drv_dly();                                   // CS hold
    GPIOC->BSRR = (uint32_t)(1u << i);           // CS_i HIGH
    drv_dly();                                   // inter-frame gap
}

static uint8_t drv_read (uint8_t i, uint8_t reg)
{
    uint8_t v;
    GPIOC->BSRR = (uint32_t)(1u << i) << 16;     // CS_i LOW
    drv_dly();
    spi_xfer((uint8_t)(0x40 | (reg & 0x3F)));    // rw=1 (read)
    v = spi_xfer(0x00);                          // report byte = register data
    while(SPI1->SR & SPI_SR_BSY);
    drv_dly();
    GPIOC->BSRR = (uint32_t)(1u << i);           // CS_i HIGH
    drv_dly();
    return v;
}

// Write a register, then read it back and retry on mismatch. Returns false only
// if it never verified after several tries.
static bool drv_cfg_reg (uint8_t i, uint8_t reg, uint8_t data)
{
    for(uint8_t t = 0; t < 6; t++) {
        drv_write(i, reg, data);
        if(drv_read(i, reg) == data)
            return true;
    }
    return false;
}

// Configure one driver. EVERY config register is read-back verified (a garbled
// current/microstep/decay frame previously slipped through and caused a driver
// to run loud or fault under load). EN_OUT is enabled last.
static bool drv_configure (uint8_t i)
{
    bool ok = true;
    drv_write(i, 0x06, 0x3C | 0x80);                    // CTRL3 + CLR_FLT: clear latched UVLO/fault
    ok &= drv_cfg_reg(i, 0x10, 0xFE);                   // CTRL13: VREF_INT_EN=1
    ok &= drv_cfg_reg(i, 0x06, 0x3C);                   // CTRL3 : unlock + OCP config
    ok &= drv_cfg_reg(i, 0x04, 0x0F);                   // CTRL1 : TOFF/DECAY, EN_OUT=0
    ok &= drv_cfg_reg(i, 0x05, RTS1_DRV_MICROSTEP);     // CTRL2 : microstep, ext STEP/DIR
    ok &= drv_cfg_reg(i, 0x0E, RTS1_DRV_RUN_CURRENT);   // CTRL11: TRQ_DAC run current
    ok &= drv_cfg_reg(i, 0x0D, RTS1_DRV_HOLD_CURRENT);  // CTRL10: ISTSL hold current
    ok &= drv_cfg_reg(i, 0x04, (uint8_t)(0x0F | 0x80)); // CTRL1 : EN_OUT=1 -> outputs on
    return ok;
}

static void rts1_drv8452_init (void)
{
    // SPI1 GPIO: PA5=SCK, PA6=MISO, PA7=MOSI, AF5.
    __HAL_RCC_SPI1_CLK_ENABLE();
    GPIO_InitTypeDef sck = {
        .Pin       = GPIO_PIN_5 | GPIO_PIN_6 | GPIO_PIN_7,
        .Mode      = GPIO_MODE_AF_PP,
        .Pull      = GPIO_NOPULL,
        .Speed     = GPIO_SPEED_FREQ_HIGH,
        .Alternate = GPIO_AF5_SPI1
    };
    HAL_GPIO_Init(GPIOA, &sck);

    // Chip-selects PC0..PC4: push-pull outputs, idle HIGH (deselected).
    GPIO_InitTypeDef cs = {
        .Pin   = DRV_CS_MASK,
        .Mode  = GPIO_MODE_OUTPUT_PP,
        .Pull  = GPIO_NOPULL,
        .Speed = GPIO_SPEED_FREQ_LOW
    };
    HAL_GPIO_Init(GPIOC, &cs);
    HAL_GPIO_WritePin(GPIOC, DRV_CS_MASK, GPIO_PIN_SET);

    // SPI1 master, mode 1 (CPOL=0, CPHA=1), 8-bit, MSB-first, soft NSS.
    // BR=/32 (~2.6 MHz) for timing margin (config is one-shot, speed irrelevant).
    SPI1->CR1 = 0;
    SPI1->CR2 = 0;
    SPI1->CR1 = SPI_CR1_SSM | SPI_CR1_SSI | SPI_CR1_MSTR |
                (4u << SPI_CR1_BR_Pos) | SPI_CR1_CPHA;
    SPI1->CR1 |= SPI_CR1_SPE;

    // Flush the first-frame artifact: the first transfer(s) after SPE can be
    // garbled. Clock out dummies with all CS deasserted (no driver latches them)
    // so driver 0's real first frame (CTRL13/VREF_INT_EN) isn't the casualty -
    // that was leaving the X driver (driver 0) with no current reference.
    for(volatile int d = 0; d < 1000; d++);     // brief settle
    (void)spi_xfer(0xFF);
    (void)spi_xfer(0xFF);

    // Configure + enable all five drivers, with read-back verification + retry
    // so a single dropped SPI frame can't leave a driver silently disabled.
    for(uint8_t i = 0; i < DRV_N; i++) {
        for(uint8_t tries = 0; tries < 4; tries++) {
            if(drv_configure(i))
                break;                              // EN_OUT confirmed set
        }
    }
}

// =================== E-stop: motor-power (VM) loss monitor ===================
// The board's e-stop cuts MOTOR POWER (VM); there is no e-stop signal wire. The
// DRV8452 reports VM undervoltage in its FAULT register (0x00 bit5 = UVLO),
// readable over SPI while USB/VCC stays up. We poll it: on VM loss we raise the
// grblHAL e-stop (halt + alarm); on soft-reset we clear the latched fault and
// reconfigure the drivers, so pressing reset after power returns re-powers the
// motors (this also makes boot order not matter).
#define DRV_FAULT_REG   0x00            // R: bit7=FAULT, bit5=UVLO
#define DRV_UVLO_BIT    0x20

static volatile bool rts1_vm_fault = false;
static uint32_t rts1_poll_last = 0;
static on_execute_realtime_ptr rts1_on_realtime = NULL;
static control_signals_get_state_ptr rts1_get_state = NULL;

static control_signals_t rts1_control_get_state (void)
{
    control_signals_t s = rts1_get_state ? rts1_get_state() : (control_signals_t){0};
    if(rts1_vm_fault)
        s.e_stop = On;
    return s;
}

static void rts1_busywait (uint32_t loops) { while(loops--) __NOP(); }

// Recover the drivers after a VM-UVLO event: an SPI reconfigure alone won't
// re-enable them, so first HARDWARE-cycle their enable/power straps (PC15/PB15
// low->high resets the DRV8452 stage), then re-run the SPI config.
static void rts1_recover_drivers (void)
{
    HAL_GPIO_WritePin(GPIOC, GPIO_PIN_15, GPIO_PIN_RESET);   // straps low = drivers off
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_15, GPIO_PIN_RESET);
    rts1_busywait(1500000);                                  // ~50 ms off
    HAL_GPIO_WritePin(GPIOC, GPIO_PIN_15, GPIO_PIN_SET);     // straps high = drivers on
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_15, GPIO_PIN_SET);
    rts1_busywait(1500000);                                  // ~50 ms settle
    for(uint8_t i = 0; i < DRV_N; i++)                       // re-config over SPI
        for(uint8_t t = 0; t < 4 && !drv_configure(i); t++)
            ;
}

static void rts1_realtime (sys_state_t state)
{
    static uint8_t vm_ok = 0;
    uint32_t now = hal.get_elapsed_ticks ? hal.get_elapsed_ticks() : 0;
    if(now - rts1_poll_last >= 100) {               // poll VM ~10 Hz
        rts1_poll_last = now;
        if(!rts1_vm_fault) {
            // Healthy: a set UVLO bit means VM just dropped -> e-stop (halt+alarm).
            if(drv_read(0, DRV_FAULT_REG) & DRV_UVLO_BIT) {
                rts1_vm_fault = true;
                vm_ok = 0;
                hal.control.interrupt_callback(rts1_control_get_state());
            }
        } else {
            // Faulted: UVLO LATCHES, so clear it then re-read - re-asserts only if
            // VM is genuinely still low. Cleared & stable => VM is back: power-cycle
            // the drivers + reconfigure, then release the e-stop (no MCU reboot).
            drv_write(0, 0x06, 0x3C | 0x80);            // CLR_FLT (driver 0)
            if(drv_read(0, DRV_FAULT_REG) & DRV_UVLO_BIT)
                vm_ok = 0;                               // VM still low
            else if(++vm_ok >= 3) {                      // back & stable ~300 ms
                vm_ok = 0;
                rts1_recover_drivers();
                rts1_vm_fault = false;
                hal.control.interrupt_callback(rts1_control_get_state());
            }
        }
    }
    if(rts1_on_realtime)
        rts1_on_realtime(state);
}

static void rts1_estop_init (void)
{
    hal.signals_cap.e_stop = On;

    rts1_get_state = hal.control.get_state;
    hal.control.get_state = rts1_control_get_state;

    rts1_on_realtime = grbl.on_execute_realtime;
    grbl.on_execute_realtime = rts1_realtime;

    rts1_poll_last = hal.get_elapsed_ticks ? hal.get_elapsed_ticks() : 0;
}

void board_init (void)
{
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();

    // Master enable + board straps: PA15 LOW (rail on, fans run), PB15/PC15 HIGH.
    GPIO_InitTypeDef gpio = {
        .Pin   = GPIO_PIN_15,
        .Mode  = GPIO_MODE_OUTPUT_PP,
        .Pull  = GPIO_NOPULL,
        .Speed = GPIO_SPEED_FREQ_LOW
    };
    HAL_GPIO_Init(GPIOA, &gpio);
    HAL_GPIO_Init(GPIOB, &gpio);
    HAL_GPIO_Init(GPIOC, &gpio);
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_15, GPIO_PIN_RESET);   // MASTER ENABLE (active-low)
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_15, GPIO_PIN_SET);
    HAL_GPIO_WritePin(GPIOC, GPIO_PIN_15, GPIO_PIN_SET);

    // Bring the five DRV8452 drivers out of Hi-Z and set their current (SPI).
    rts1_drv8452_init();

    // Monitor motor power (VM): e-stop on loss, recover drivers on reset.
    rts1_estop_init();
}

#endif // BOARD_RTS1
