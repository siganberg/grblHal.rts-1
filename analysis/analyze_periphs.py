import struct, collections

IMG = open("stock_RTS-1_backup.bin","rb").read()
BASE = 0x08000000

# STM32F401 peripheral base addresses
PERIPH = {
 0x40000000:"TIM2",0x40000400:"TIM3",0x40000800:"TIM4",0x40000C00:"TIM5",
 0x40002800:"RTC",0x40002C00:"WWDG",0x40003000:"IWDG",
 0x40003800:"SPI2/I2S2",0x40003C00:"SPI3/I2S3",
 0x40004400:"USART2",0x40005400:"I2C1",0x40005800:"I2C2",0x40005C00:"I2C3",0x40007000:"PWR",
 0x40010000:"TIM1",0x40011000:"USART1",0x40011400:"USART6",0x40012000:"ADC1",
 0x40012C00:"SDIO",0x40013000:"SPI1",0x40013400:"SPI4",0x40013800:"SYSCFG",0x40013C00:"EXTI",
 0x40014000:"TIM9",0x40014400:"TIM10",0x40014800:"TIM11",
 0x40020000:"GPIOA",0x40020400:"GPIOB",0x40020800:"GPIOC",0x40020C00:"GPIOD",0x40021000:"GPIOE",0x40021C00:"GPIOH",
 0x40023000:"CRC",0x40023800:"RCC",0x40023C00:"FLASH",0x40026000:"DMA1",0x40026400:"DMA2",
 0x50000000:"USB_OTG_FS",
}
# register offset names per family
GPIO_REG={0x00:"MODER",0x04:"OTYPER",0x08:"OSPEEDR",0x0C:"PUPDR",0x10:"IDR",0x14:"ODR",0x18:"BSRR",0x1C:"LCKR",0x20:"AFRL",0x24:"AFRH"}
TIM_REG={0x00:"CR1",0x04:"CR2",0x08:"SMCR",0x0C:"DIER",0x10:"SR",0x14:"EGR",0x18:"CCMR1",0x1C:"CCMR2",0x20:"CCER",0x24:"CNT",0x28:"PSC",0x2C:"ARR",0x30:"RCR",0x34:"CCR1",0x38:"CCR2",0x3C:"CCR3",0x40:"CCR4",0x44:"BDTR"}
USART_REG={0x00:"SR",0x04:"DR",0x08:"BRR",0x0C:"CR1",0x10:"CR2",0x14:"CR3",0x18:"GTPR"}

def which(addr):
    base = addr & ~0x3FF
    if base in PERIPH:
        return PERIPH[base], addr-base
    return None,None

# scan 4-byte aligned words for peripheral base/register literals
refs = collections.defaultdict(lambda: collections.Counter())
basehit = collections.Counter()
for off in range(0, len(IMG)-3, 4):
    w = struct.unpack_from("<I", IMG, off)[0]
    if 0x40000000 <= w < 0x40080000 or 0x50000000 <= w < 0x50060000:
        name, roff = which(w)
        if name:
            basehit[name]+=1
            refs[name][roff]+=1

print("=== PERIPHERAL USAGE (from literal-pool references) ===")
print(f"{'PERIPH':12} {'refs':>4}  registers touched (offset:count)")
def regname(periph,off):
    if periph.startswith("GPIO"): return GPIO_REG.get(off,f"+0x{off:02X}")
    if periph.startswith("TIM"):  return TIM_REG.get(off,f"+0x{off:02X}")
    if periph.startswith("USART"):return USART_REG.get(off,f"+0x{off:02X}")
    return f"+0x{off:02X}"
for name in sorted(basehit, key=lambda n:-basehit[n]):
    regs = refs[name]
    reglist = ", ".join(f"{regname(name,o)}({c})" for o,c in sorted(regs.items()))
    print(f"{name:12} {basehit[name]:>4}  {reglist}")
