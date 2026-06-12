import struct, collections
from capstone import *
from capstone.arm import *
IMG=open("stock_RTS-1_backup.bin","rb").read(); BASE=0x08000000
def rd32(a):
    o=a-BASE; return struct.unpack_from("<I",IMG,o)[0] if 0<=o<=len(IMG)-4 else None
GPIO={0x40020000:"PA",0x40020400:"PB",0x40020800:"PC",0x40020C00:"PD",0x40021000:"PE",0x40021C00:"PH"}
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB); md.detail=True
WRITEPIN=0x08019EC4; READPIN=0x08019EB8; INIT=0x08002114

starts=set()
for o in range(0,len(IMG)-1,2):
    hw=struct.unpack_from("<H",IMG,o)[0]
    if 0xB500<=hw<=0xB5FF: starts.add(o)
    if hw==0xE92D and (struct.unpack_from("<H",IMG,o+2)[0]&0x4000): starts.add(o)
starts=sorted(starts)

write_pins=collections.Counter(); read_pins=collections.Counter()
bsrr=collections.defaultdict(set)          # port -> pins toggled directly
init_calls=[]                               # (port,pinmask,mode,pull,alt)

def analyze(start,end):
    reg={}; sp_tag={}; stack={}
    for ins in md.disasm(IMG[start:end], BASE+start):
        m=ins.mnemonic; b=m.split('.')[0]; ops=ins.operands
        if b=='bl':
            tgt=ops[0].imm if ops and ops[0].type==ARM_OP_IMM else None
            port=GPIO.get(reg.get('r0')); pm=reg.get('r1')
            if tgt==WRITEPIN and port and pm and (pm&(pm-1))==0 and pm<=0x8000:
                write_pins[(port,pm.bit_length()-1)]+=1
            if tgt==READPIN and port and pm and (pm&(pm-1))==0 and pm<=0x8000:
                read_pins[(port,pm.bit_length()-1)]+=1
            if tgt==INIT and port and 'r1' in sp_tag:
                sb=sp_tag['r1']
                init_calls.append((port,stack.get(sb),stack.get(sb+4),stack.get(sb+8),stack.get(sb+16)))
            for r in('r0','r1','r2','r3','r12'): reg.pop(r,None); sp_tag.pop(r,None)
            continue
        if b in('b','bx','blx','cbz','cbnz'): continue
        try:
            if m.startswith('ldr') and ops[1].type==ARM_OP_MEM and ops[1].mem.base==ARM_REG_PC:
                d=ins.reg_name(ops[0].reg); v=rd32(((ins.address+4)&~3)+ops[1].mem.disp)
                if v is not None: reg[d]=v; sp_tag.pop(d,None)
                else: reg.pop(d,None)
            elif m=='movw': reg[ins.reg_name(ops[0].reg)]=ops[1].imm&0xFFFF; sp_tag.pop(ins.reg_name(ops[0].reg),None)
            elif m=='movt':
                d=ins.reg_name(ops[0].reg); reg[d]=(reg.get(d,0)&0xFFFF)|((ops[1].imm&0xFFFF)<<16)
            elif m in('mov','movs','mov.w') and ops[1].type==ARM_OP_IMM:
                reg[ins.reg_name(ops[0].reg)]=ops[1].imm&0xFFFFFFFF; sp_tag.pop(ins.reg_name(ops[0].reg),None)
            elif m in('mov','mov.w') and ops[1].type==ARM_OP_REG:
                s=ins.reg_name(ops[1].reg);d=ins.reg_name(ops[0].reg)
                if s=='sp': sp_tag[d]=0; reg.pop(d,None)
                elif s in reg: reg[d]=reg[s]; sp_tag.pop(d,None)
                elif s in sp_tag: sp_tag[d]=sp_tag[s]; reg.pop(d,None)
                else: reg.pop(d,None); sp_tag.pop(d,None)
            elif b in('add','adds') and len(ops)==3 and ops[1].type==ARM_OP_REG and ins.reg_name(ops[1].reg)=='sp' and ops[2].type==ARM_OP_IMM:
                sp_tag[ins.reg_name(ops[0].reg)]=ops[2].imm; reg.pop(ins.reg_name(ops[0].reg),None)
            elif m.startswith('str') and ops[1].type==ARM_OP_MEM:
                mem=ops[1].mem; src=ins.reg_name(ops[0].reg); bse=ins.reg_name(mem.base) if mem.base else None
                if bse=='sp' and src in reg: stack[mem.disp]=reg[src]
                elif bse in sp_tag and src in reg: stack[sp_tag[bse]+mem.disp]=reg[src]
                elif bse in reg and reg[bse] in GPIO and mem.disp==0x18 and src in reg:
                    val=reg[src]
                    for p in range(16):
                        if (val>>p)&1 or (val>>(p+16))&1: bsrr[GPIO[reg[bse]]].add(p)
            elif ops and ops[0].type==ARM_OP_REG:
                d=ins.reg_name(ops[0].reg); reg.pop(d,None); sp_tag.pop(d,None)
        except: pass

for i,s in enumerate(starts):
    e=starts[i+1] if i+1<len(starts) else len(IMG)
    if 4<e-s<4000: analyze(s,e)

def fmt(cnt):
    d=collections.defaultdict(list)
    for (port,pin),c in cnt.items(): d[port].append(pin)
    return {p:sorted(v) for p,v in d.items()}

print("=== OUTPUT pins (HAL_GPIO_WritePin) — DIR / ENABLE / spindle / VFD-dir / relays ===")
for p,v in sorted(fmt(write_pins).items()): print(f"   {p}: {v}")
print("\n=== INPUT pins (HAL_GPIO_ReadPin) — limits / probe / toolsetter / estop ===")
for p,v in sorted(fmt(read_pins).items()): print(f"   {p}: {v}")
print("\n=== Direct BSRR-toggled pins (STEP pulses / fast outputs) ===")
for p in sorted(bsrr): print(f"   {p}: {sorted(bsrr[p])}")

# AF table resolution
AF={
 ('PA',9):{7:'USART1_TX',1:'TIM1_CH2'},('PA',10):{7:'USART1_RX',1:'TIM1_CH3'},
 ('PA',8):{1:'TIM1_CH1',7:'USART1_CK'},('PA',11):{8:'USART6_TX',1:'TIM1_CH4'},('PA',12):{8:'USART6_RX'},
 ('PB',6):{7:'USART1_TX',2:'TIM4_CH1'},('PB',7):{7:'USART1_RX',2:'TIM4_CH2'},
 ('PA',2):{7:'USART2_TX',1:'TIM2_CH3',2:'TIM5_CH3',3:'TIM9_CH1'},('PA',3):{7:'USART2_RX',1:'TIM2_CH4',2:'TIM5_CH4',3:'TIM9_CH2'},
 ('PC',6):{8:'USART6_TX',2:'TIM3_CH1'},('PC',7):{8:'USART6_RX',2:'TIM3_CH2'},
 ('PA',5):{5:'SPI1_SCK',1:'TIM2_CH1'},('PA',6):{5:'SPI1_MISO',2:'TIM3_CH1'},('PA',7):{5:'SPI1_MOSI',2:'TIM3_CH2'},
 ('PB',3):{5:'SPI1_SCK',1:'TIM2_CH2'},('PB',4):{5:'SPI1_MISO',2:'TIM3_CH1'},('PB',5):{5:'SPI1_MOSI',2:'TIM3_CH2'},
 ('PB',13):{1:'TIM1_CH1N',5:'SPI2_SCK'},('PB',14):{1:'TIM1_CH2N'},('PB',15):{1:'TIM1_CH3N'},
 ('PA',0):{1:'TIM2_CH1',2:'TIM5_CH1'},('PA',1):{1:'TIM2_CH2',2:'TIM5_CH2'},
 ('PB',10):{1:'TIM2_CH3',5:'SPI2_SCK'},('PB',0):{2:'TIM3_CH3'},('PB',1):{2:'TIM3_CH4'},
 ('PB',8):{2:'TIM4_CH3',3:'TIM10_CH1'},('PB',9):{2:'TIM4_CH4',3:'TIM11_CH1'},
}
MODE={0x0:'INPUT',0x1:'OUT_PP',0x11:'OUT_OD',0x2:'AF',0x12:'AF_OD',0x3:'ANALOG'}
print("\n=== HAL_GPIO_Init decoded (mode + alternate function) ===")
seen=set()
for port,pinmask,mode,pull,alt in init_calls:
    if pinmask is None or mode is None: continue
    for p in range(16):
        if (pinmask>>p)&1:
            ml=mode&0xFFFF; exti=(mode>>16)!=0
            label='INPUT_IT' if exti else MODE.get(ml,f'0x{ml:X}')
            sig=''
            if ml in(0x2,0x12) and alt is not None:
                sig=AF.get((port,p),{}).get(alt, f'AF{alt}')
            key=(port,p,label,sig)
            if key in seen: continue
            seen.add(key)
            print(f"   {port}{p:<2} {label:<9} {('-> '+sig) if sig else ''}")
