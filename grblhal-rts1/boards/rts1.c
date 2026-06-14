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
// Stock RTS-1 target: run 2.8 A, hold 0.75 A, 1/16 microstep. The TRQ_DAC->amps
// mapping (board full-scale) is unknown; 0xFF over-drove the motors (overcurrent
// dropout on X/Y1), so use 0xC0 which was stable. Tune once a scope/logic-analyzer
// confirms the exact value stock writes for 2.8 A.
#define RTS1_DRV_RUN_CURRENT   0xC0   // CTRL11 TRQ_DAC (move)  ~2.8 A target (stable)
#define RTS1_DRV_HOLD_CURRENT  0x40   // CTRL10 ISTSL  (idle)   ~0.75 A target
#define RTS1_DRV_MICROSTEP     0x06   // CTRL2 low nibble: 0x06 = 1/16 (stock); $100-102 = 320/320/800

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

static void rts1_busywait (uint32_t loops) { while(loops--) __NOP(); }

// Stock resets the DRV8452s by pulsing PC15 (the driver reset/enable strap) LOW
// then HIGH before SPI config (RE: config routine @0x0800D7E4 does PC15=0; delay
// 1 ms; PC15=1). A steady-high PC15 works at cold boot, but a driver stuck after
// a VM-UVLO event ONLY recovers via this LOW->HIGH pulse - which is why even an
// MCU reboot (PC15 re-driven high, never pulsed low) failed to recover it.
static void rts1_drv_reset_pulse (void)
{
    HAL_GPIO_WritePin(GPIOC, GPIO_PIN_15, GPIO_PIN_RESET);   // assert reset
    rts1_busywait(90000);                                    // ~1 ms low (matches stock)
    HAL_GPIO_WritePin(GPIOC, GPIO_PIN_15, GPIO_PIN_SET);     // release
    rts1_busywait(180000);                                   // ~2 ms settle (matches stock)
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

    // Reset the drivers (PC15 pulse) before configuring - matches stock and is
    // what lets a UVLO-stuck driver recover.
    rts1_drv_reset_pulse();

    // Configure + enable all five drivers, with read-back verification + retry
    // so a single dropped SPI frame can't leave a driver silently disabled.
    for(uint8_t i = 0; i < DRV_N; i++) {
        for(uint8_t tries = 0; tries < 4; tries++) {
            if(drv_configure(i))
                break;                              // EN_OUT confirmed set
        }
    }
}

// ======================= Diagnostics (logging + $DRV) =======================
// RTS1_DIAG=1 streams e-stop/recovery events to the console and dumps the live
// DRV8452 registers at boot + on every fault transition, and enables the "$DRV"
// command (dump all five drivers' registers on demand). Set to 0 to ship quiet.
#ifndef RTS1_DIAG
#define RTS1_DIAG 1
#endif

static const char rts1_hexd[] = "0123456789ABCDEF";

static void rts1_emit (const char *s) { if(hal.stream.write) hal.stream.write(s); }

// Append "0xNN" for a byte into buf at *p.
static void rts1_puthex (char *buf, uint8_t *p, uint8_t v)
{
    buf[(*p)++] = '0'; buf[(*p)++] = 'x';
    buf[(*p)++] = rts1_hexd[(v >> 4) & 0xF];
    buf[(*p)++] = rts1_hexd[v & 0xF];
}

// Read the key DRV8452 registers from all five drivers and stream them as
// [MSG:DRVi ...] lines. On a no-config snapshot build this reads stock's LIVE
// values; on this (configured) build it confirms our writes + the read path.
static void rts1_dump_registers (void)
{
    static const struct { char nm[4]; uint8_t reg; } regs[] = {
        {"F",  0x00}, {"C1", 0x04}, {"C2",  0x05}, {"C3",  0x06}, {"C5", 0x08},
        {"C6", 0x09}, {"C10",0x0D}, {"C11", 0x0E}, {"C13", 0x10}
    };
    for(uint8_t i = 0; i < DRV_N; i++) {
        char buf[128]; uint8_t p = 0;
        const char *h = "[MSG:DRV"; while(*h) buf[p++] = *h++;
        buf[p++] = (char)('0' + i);
        for(uint8_t r = 0; r < sizeof(regs) / sizeof(regs[0]); r++) {
            buf[p++] = ' ';
            const char *nm = regs[r].nm; while(*nm) buf[p++] = *nm++;
            buf[p++] = '=';
            rts1_puthex(buf, &p, drv_read(i, regs[r].reg));
        }
        buf[p++] = ']'; buf[p++] = '\r'; buf[p++] = '\n'; buf[p] = '\0';
        rts1_emit(buf);
    }
}

static on_unknown_sys_command_ptr rts1_on_sys_command = NULL;

static status_code_t rts1_sys_command (sys_state_t state, char *line)
{
    if(!strcmp(line, "DRV")) {                       // "$DRV": dump driver regs
        rts1_dump_registers();
        return Status_OK;
    }
    return rts1_on_sys_command ? rts1_on_sys_command(state, line) : Status_Unhandled;
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

// Recover the drivers after a VM-UVLO event (or a brown-out reboot with VM back):
// pulse PC15 (nSLEEP) to reset the DRV8452s, then re-config with READ-BACK VERIFY
// + retry per driver (reads are confirmed working via $DRV), so a dropped frame on
// the just-woken interface can't leave a driver silently disabled. Logs the post-
// recovery CTRL1 (expect 0x8F = EN_OUT on) + FAULT (expect 0x00) so the console
// proves whether the motors actually re-grabbed.
// Returns true only if ALL drivers verified re-enabled (CTRL1 = 0x8F, no fault).
static bool rts1_recover_drivers (void)
{
    bool all_ok = true;
    rts1_drv_reset_pulse();                                  // PC15 low->high reset (like stock)
    for(uint8_t i = 0; i < DRV_N; i++) {
        bool ok = false;
        for(uint8_t t = 0; t < 4 && !ok; t++)
            ok = drv_configure(i);                           // verified write + retry
        all_ok &= ok;
#if RTS1_DIAG
        uint8_t c1 = drv_read(i, 0x04), f = drv_read(i, DRV_FAULT_REG);
        char b[80]; uint8_t p = 0;
        const char *h = "[MSG:RTS1 recov DRV"; while(*h) b[p++] = *h++;
        b[p++] = (char)('0' + i);
        const char *st = ok ? " OK" : " FAIL"; while(*st) b[p++] = *st++;
        const char *cc = " C1="; while(*cc) b[p++] = *cc++; rts1_puthex(b, &p, c1);
        const char *ff = " F=";  while(*ff) b[p++] = *ff++; rts1_puthex(b, &p, f);
        b[p++] = ']'; b[p++] = '\r'; b[p++] = '\n'; b[p] = '\0';
        rts1_emit(b);
#endif
    }
    return all_ok;
}

// Emit "[MSG:RTS1 <tag>=0xNN]".
static void rts1_log_byte (const char *tag, uint8_t v)
{
    char b[64]; uint8_t p = 0;
    const char *h = "[MSG:RTS1 "; while(*h) b[p++] = *h++;
    while(*tag) b[p++] = *tag++;
    b[p++] = '=';
    rts1_puthex(b, &p, v);
    b[p++] = ']'; b[p++] = '\r'; b[p++] = '\n'; b[p] = '\0';
    rts1_emit(b);
}

static void rts1_realtime (sys_state_t state)
{
    uint32_t now = hal.get_elapsed_ticks ? hal.get_elapsed_ticks() : 0;

#if RTS1_DIAG
    static bool booted = false;                     // one-shot boot dump (stream up)
    if(!booted && now > 2500) {
        booted = true;
        rts1_emit("[MSG:RTS1 diag build - $DRV dumps driver regs; e-stop logged]" ASCII_EOL);
        rts1_dump_registers();
    }
#endif

    if(now - rts1_poll_last >= 100) {               // poll VM ~10 Hz
        rts1_poll_last = now;
        if(!rts1_vm_fault) {
            // Healthy: a set UVLO bit means VM just dropped -> e-stop (halt+alarm).
            uint8_t fault = drv_read(0, DRV_FAULT_REG);
            if(fault & DRV_UVLO_BIT) {
                rts1_vm_fault = true;
#if RTS1_DIAG
                rts1_log_byte("VM-LOST fault", fault);
#endif
                hal.control.interrupt_callback(rts1_control_get_state());
            }
        } else {
            // Faulted (VM lost). The e-stop cuts the DRIVERS' logic supply too, so
            // while it is held the DRV8452s are fully dark and every SPI read returns
            // 0x00 - which is NOT a real "no fault", just an unpowered chip. So the
            // FAULT register is untrustworthy here. Instead probe LIVENESS: write a
            // sentinel (CTRL3=0x3C, our normal value) and read it back - only a
            // powered chip echoes it. While dark we wait quietly (no PC15 pulse, no
            // spam). Once the chip is alive again (VM restored) and stable, do one
            // verified recovery and release the e-stop only when all outputs confirm
            // back on (CTRL1=0x8F); otherwise keep retrying.
            static uint8_t vm_back = 0;

            drv_write(0, 0x06, 0x3C);                   // liveness sentinel (= our CTRL3)
            if(drv_read(0, 0x06) != 0x3C) {
                vm_back = 0;                            // chip dark -> VM still down, wait
            } else if(++vm_back >= 3) {                 // chip alive & stable ~300 ms
                vm_back = 0;
#if RTS1_DIAG
                rts1_emit("[MSG:RTS1 VM back - recovering]" ASCII_EOL);
#endif
                if(rts1_recover_drivers()) {            // verified: every EN_OUT back on
                    rts1_vm_fault = false;
#if RTS1_DIAG
                    rts1_emit("[MSG:RTS1 VM RESTORED - motors re-enabled]" ASCII_EOL);
#endif
                    hal.control.interrupt_callback(rts1_control_get_state());
                }
#if RTS1_DIAG
                else rts1_emit("[MSG:RTS1 recovery incomplete - retrying]" ASCII_EOL);
#endif
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

    rts1_on_sys_command = grbl.on_unknown_sys_command;   // "$DRV" register dump
    grbl.on_unknown_sys_command = rts1_sys_command;

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
