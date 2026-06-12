import struct, collections
from capstone import *
from capstone.arm import *

IMG = open("stock_RTS-1_backup.bin","rb").read()
BASE = 0x08000000
def rd32(addr):
    o = addr-BASE
    if 0<=o<=len(IMG)-4: return struct.unpack_from("<I",IMG,o)[0]
    return None

GPIO_BASES={0x40020000:"PA",0x40020400:"PB",0x40020800:"PC",0x40020C00:"PD",0x40021000:"PE",0x40021C00:"PH"}
def periph_of(addr):
    b=addr & ~0x3FF
    return b, addr-b

md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
md.detail = True

# ---- linear sweep with light register tracking ----
reg={}            # regname -> value
or_imm={}         # regname -> last OR immediate (for RMW decode)
def inval(r):
    reg.pop(r,None); or_imm.pop(r,None)

afr_writes=[]     # (port, 'AFRL'/'AFRH', value)
moder_writes=[]   # (port, value)
pupdr_writes=[]   # (port, value)
otyper_writes=[]
bsrr_writes=[]    # (port, value)
tim_writes=[]     # (timbase, off, value)
usart_writes=[]   # (usartbase, off, value)
gpio_reg={0:'MODER',4:'OTYPER',8:'OSPEEDR',0xC:'PUPDR',0x18:'BSRR',0x20:'AFRL',0x24:'AFRH'}

code = IMG
for ins in md.disasm(code, BASE):
    m=ins.mnemonic; ops=ins.operands
    # branches / control flow -> reset tracker
    if m.split('.')[0] in ('b','bl','bx','blx','cbz','cbnz','bne','beq','bgt','blt','bge','ble','bhi','bls','pop','push','it','ite','itt','ittt','itte'):
        reg.clear(); or_imm.clear(); continue
    try:
        if m.startswith('ldr') and len(ops)==2 and ops[1].type==ARM_OP_MEM:
            mem=ops[1].mem; dst=ins.reg_name(ops[0].reg)
            if mem.base==ARM_REG_PC:
                lit=((ins.address+4)&~3)+mem.disp
                v=rd32(lit)
                if v is not None: reg[dst]=v; or_imm.pop(dst,None)
                else: inval(dst)
            else:
                inval(dst)
        elif m in ('movw',) and len(ops)==2 and ops[1].type==ARM_OP_IMM:
            reg[ins.reg_name(ops[0].reg)]=ops[1].imm & 0xFFFF; 
        elif m in ('movt',) and len(ops)==2 and ops[1].type==ARM_OP_IMM:
            d=ins.reg_name(ops[0].reg); reg[d]=(reg.get(d,0)&0xFFFF)|((ops[1].imm&0xFFFF)<<16)
        elif m in ('mov','mov.w','movs') and len(ops)==2 and ops[1].type==ARM_OP_IMM:
            reg[ins.reg_name(ops[0].reg)]=ops[1].imm & 0xFFFFFFFF; or_imm.pop(ins.reg_name(ops[0].reg),None)
        elif m in ('mov','mov.w') and len(ops)==2 and ops[1].type==ARM_OP_REG:
            s=ins.reg_name(ops[1].reg); d=ins.reg_name(ops[0].reg)
            if s in reg: reg[d]=reg[s]
            else: inval(d)
        elif m in ('orr','orr.w','orrs') and ops[-1].type==ARM_OP_IMM:
            d=ins.reg_name(ops[0].reg); or_imm[d]=ops[-1].imm & 0xFFFFFFFF; reg.pop(d,None)
        elif m in ('add','add.w','adds') and len(ops)==3 and ops[2].type==ARM_OP_IMM:
            s=ins.reg_name(ops[1].reg); d=ins.reg_name(ops[0].reg)
            if s in reg: reg[d]=(reg[s]+ops[2].imm)&0xFFFFFFFF
            else: inval(d)
        elif m.startswith('str') and len(ops)==2 and ops[1].type==ARM_OP_MEM:
            mem=ops[1].mem; src=ins.reg_name(ops[0].reg); base=ins.reg_name(mem.base) if mem.base!=0 else None
            if base in reg and mem.index==0:
                addr=(reg[base]+mem.disp)&0xFFFFFFFF
                pbase,off=periph_of(addr)
                val = reg.get(src, None)
                orv = or_imm.get(src, None)
                use = val if val is not None else orv
                if pbase in GPIO_BASES and use is not None:
                    port=GPIO_BASES[pbase]
                    if off==0x20: afr_writes.append((port,'AFRL',use))
                    elif off==0x24: afr_writes.append((port,'AFRH',use))
                    elif off==0x00: moder_writes.append((port,use))
                    elif off==0x0C: pupdr_writes.append((port,use))
                    elif off==0x04: otyper_writes.append((port,use))
                    elif off==0x18: bsrr_writes.append((port,use))
                elif 0x40000000<=pbase<0x40000C00+1 or pbase in (0x40010000,0x40014000,0x40014400,0x40014800):
                    if use is not None: tim_writes.append((pbase,off,use))
                elif pbase in (0x40011000,0x40011400,0x40004400):
                    if use is not None: usart_writes.append((pbase,off,use))
            # store to [base] doesn't change base reg
    except Exception:
        pass

# ---- decode AFR (alternate function) assignments ----
AFCLASS={0:"SYS/SWD",1:"TIM1/2",2:"TIM3/4/5",3:"TIM9/10/11",4:"I2C1/2/3",5:"SPI1/2/4",6:"SPI3",7:"USART1/2",8:"USART6",9:"I2C2/3",10:"USB_FS",15:"EVOUT"}
print("=== ALTERNATE-FUNCTION PIN ASSIGNMENTS (AFR writes) ===")
seen=set()
afmap=collections.defaultdict(dict)
for port,reg_,val in afr_writes:
    lowpin = 0 if reg_=='AFRL' else 8
    for nib in range(8):
        af=(val>>(4*nib))&0xF
        if af!=0:
            pin=lowpin+nib
            afmap[port][pin]=af
for port in sorted(afmap):
    for pin in sorted(afmap[port]):
        af=afmap[port][pin]
        print(f"  {port}{pin:<2} -> AF{af:<2} ({AFCLASS.get(af,'?')})")

# ---- decode MODER: classify pins ----
def classify_moder(val):
    out={}
    for pin in range(16):
        mode=(val>>(2*pin))&0x3
        if mode!=0: out[pin]={1:'OUT',2:'AF',3:'ANALOG'}[mode]
    return out
print("\n=== MODER writes (pin direction; OUT=GPIO output, AF=peripheral, ANALOG=ADC) ===")
agg=collections.defaultdict(dict)
for port,val in moder_writes:
    for pin,k in classify_moder(val).items():
        agg[port][pin]=k
for port in sorted(agg):
    items=", ".join(f"{port}{p}:{agg[port][p]}" for p in sorted(agg[port]))
    print(f"  {port}: {items}")

# ---- BSRR runtime-toggled output pins (STEP/DIR/EN/spindle/VFD-dir candidates) ----
print("\n=== BSRR-toggled output pins (runtime set/reset = active control signals) ===")
bsrr_pins=collections.defaultdict(set)
for port,val in bsrr_writes:
    for pin in range(16):
        if (val>>pin)&1: bsrr_pins[port].add(pin)          # set
        if (val>>(pin+16))&1: bsrr_pins[port].add(pin)     # reset
for port in sorted(bsrr_pins):
    print(f"  {port}: pins {sorted(bsrr_pins[port])}")

# ---- timers: which channels enabled (CCER) & PWM mode (CCMR) ----
TIMNAME={0x40010000:"TIM1",0x40000000:"TIM2",0x40000400:"TIM3",0x40000800:"TIM4",0x40000C00:"TIM5",0x40014000:"TIM9",0x40014400:"TIM10",0x40014800:"TIM11"}
print("\n=== TIMER config writes (CCER=channel enable, CCMR=PWM mode, ARR/PSC=timing) ===")
TR={0x18:"CCMR1",0x1C:"CCMR2",0x20:"CCER",0x28:"PSC",0x2C:"ARR",0x34:"CCR1",0x38:"CCR2",0x3C:"CCR3",0x40:"CCR4",0x00:"CR1"}
tim_agg=collections.defaultdict(dict)
for base,off,val in tim_writes:
    if base in TIMNAME and off in TR:
        tim_agg[TIMNAME[base]][TR[off]]=val
for t in sorted(tim_agg):
    parts=", ".join(f"{r}=0x{tim_agg[t][r]:X}" for r in tim_agg[t])
    print(f"  {t}: {parts}")

# ---- USART config ----
UN={0x40011000:"USART1",0x40011400:"USART6",0x40004400:"USART2"}
UR={0x08:"BRR",0x0C:"CR1",0x10:"CR2",0x14:"CR3"}
print("\n=== USART config writes ===")
us_agg=collections.defaultdict(dict)
for base,off,val in usart_writes:
    if base in UN and off in UR: us_agg[UN[base]][UR[off]]=val
for u in sorted(us_agg):
    print(f"  {u}: "+", ".join(f"{r}=0x{us_agg[u][r]:X}" for r in us_agg[u]))
