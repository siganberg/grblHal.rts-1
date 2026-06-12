import struct, collections
from capstone import *
from capstone.arm import *
IMG=open("stock_RTS-1_backup.bin","rb").read(); BASE=0x08000000
def rd32(a):
    o=a-BASE; return struct.unpack_from("<I",IMG,o)[0] if 0<=o<=len(IMG)-4 else None
GPIO={0x40020000:"PA",0x40020400:"PB",0x40020800:"PC",0x40020C00:"PD",0x40021000:"PE",0x40021C00:"PH"}
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB); md.detail=True
INIT=0x08019B48
starts=set()
for o in range(0,len(IMG)-1,2):
    hw=struct.unpack_from("<H",IMG,o)[0]
    if 0xB500<=hw<=0xB5FF: starts.add(o)
    if hw==0xE92D and (struct.unpack_from("<H",IMG,o+2)[0]&0x4000): starts.add(o)
starts=sorted(starts)
funcs=[(s,(starts[i+1] if i+1<len(starts) else len(IMG))) for i,s in enumerate(starts)]
inits=[]
def analyze(start,end):
    reg={'r4':None}; sp_tag={}; stack={}; dreg={}
    for ins in md.disasm(IMG[start:end], BASE+start):
        m=ins.mnemonic; b=m.split('.')[0]; ops=ins.operands
        if b=='bl':
            tgt=ops[0].imm if ops and ops[0].type==ARM_OP_IMM else None
            if tgt==INIT:
                port=GPIO.get(reg.get('r0')); sb=sp_tag.get('r1')
                if port is not None and sb is not None:
                    inits.append((port,stack.get(sb),stack.get(sb+4),stack.get(sb+8),stack.get(sb+12),stack.get(sb+16),ins.address))
            for r in('r0','r1','r2','r3','r12'): reg.pop(r,None); sp_tag.pop(r,None)
            continue
        if b in('b','bx','blx','cbz','cbnz'): continue
        try:
            if m.startswith('vldr') and ops[1].type==ARM_OP_MEM and ops[1].mem.base==ARM_REG_PC:
                d=ins.reg_name(ops[0].reg); a=((ins.address+4)&~3)+ops[1].mem.disp
                dreg[d]=(rd32(a),rd32(a+4))
            elif m.startswith('vstr') and ops[1].type==ARM_OP_MEM:
                d=ins.reg_name(ops[0].reg); mem=ops[1].mem; bse=ins.reg_name(mem.base) if mem.base else None
                if d in dreg:
                    lo,hi=dreg[d]
                    if bse=='sp': stack[mem.disp]=lo; stack[mem.disp+4]=hi
                    elif bse in sp_tag: stack[sp_tag[bse]+mem.disp]=lo; stack[sp_tag[bse]+mem.disp+4]=hi
            elif m=='strd':
                ra=ins.reg_name(ops[0].reg); rb=ins.reg_name(ops[1].reg); mem=ops[2].mem
                bse=ins.reg_name(mem.base) if mem.base else None
                base_off=None
                if bse=='sp': base_off=mem.disp
                elif bse in sp_tag: base_off=sp_tag[bse]+mem.disp
                if base_off is not None:
                    stack[base_off]=reg.get(ra); stack[base_off+4]=reg.get(rb)
            elif m.startswith('ldr') and ops[1].type==ARM_OP_MEM and ops[1].mem.base==ARM_REG_PC:
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
                else: reg.pop(d,None); sp_tag.pop(d,None)
            elif b in('add','adds','add.w') and len(ops)>=2 and ins.reg_name(ops[1].reg if len(ops)==3 else ops[0].reg)=='sp':
                if len(ops)==3 and ops[2].type==ARM_OP_IMM:
                    sp_tag[ins.reg_name(ops[0].reg)]=ops[2].imm; reg.pop(ins.reg_name(ops[0].reg),None)
            elif m.startswith('str') and len(ops)==2 and ops[1].type==ARM_OP_MEM:
                mem=ops[1].mem; src=ins.reg_name(ops[0].reg); bse=ins.reg_name(mem.base) if mem.base else None
                if bse=='sp' and src in reg: stack[mem.disp]=reg[src]
                elif bse in sp_tag and src in reg: stack[sp_tag[bse]+mem.disp]=reg[src]
            elif ops and ops[0].type==ARM_OP_REG and m not in ('cmp','cmn','tst','teq'):
                d=ins.reg_name(ops[0].reg); reg.pop(d,None); sp_tag.pop(d,None)
        except Exception: pass
for s,e in funcs:
    if 4<e-s<6000: analyze(s,e)

MODE={0x0:'INPUT',0x1:'OUT_PP',0x11:'OUT_OD',0x2:'AF_PP',0x12:'AF_OD',0x3:'ANALOG'}
PULL={0:'',1:'PU',2:'PD',None:'?'}
SPD={0:'low',1:'med',2:'high',3:'vhigh',None:'?'}
AFNAME={('PA',9):'USART1_TX',('PA',10):'USART1_RX',('PA',8):'TIM1_CH1?',('PA',2):'TIM/USART2',('PA',3):'TIM/USART2',
        ('PA',5):'SPI1_SCK',('PA',6):'SPI1_MISO/TIM3',('PA',7):'SPI1_MOSI/TIM3',('PB',6):'USART1_TX/TIM4',('PB',7):'USART1_RX/TIM4',
        ('PC',6):'USART6_TX/TIM3_CH1',('PC',7):'USART6_RX/TIM3_CH2',('PB',10):'TIM2_CH3/USART3',('PB',0):'TIM3_CH3',('PB',1):'TIM3_CH4',
        ('PB',8):'TIM4_CH3/TIM10',('PB',9):'TIM4_CH4/TIM11',('PA',0):'TIM2/5_CH1',('PA',1):'TIM2/5_CH2'}
rows={}
for port,pinm,mode,pull,spd,alt,addr in inits:
    if pinm is None or mode is None: continue
    for p in range(16):
        if (pinm>>p)&1:
            ml=mode&0xFFFF; exti=mode>>16
            if exti:
                lab='IN_'+{0x1011:'RISE',0x1021:'FALL',0x1031:'BOTH'}.get(exti,'IT')
            else: lab=MODE.get(ml,f'm0x{ml:X}')
            sig=f"AF{alt}" if ml in(0x2,0x12) else ''
            rows[(port,p)]=(lab,PULL.get(pull,'?'),SPD.get(spd,'?'),sig)
print(f"=== FULL PIN CONFIG from {len(inits)} HAL_GPIO_Init calls -> {len(rows)} pins ===")
for (port,p) in sorted(rows,key=lambda k:(k[0],k[1])):
    lab,pull,spd,sig=rows[(port,p)]
    name=AFNAME.get((port,p),'') if sig else ''
    print(f"   {port}{p:<2} {lab:<10} {pull:<3} {spd:<5} {sig:<4} {name}")
