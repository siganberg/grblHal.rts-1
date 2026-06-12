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
    reg={}; sp_tag={}; stack={}
    for ins in md.disasm(IMG[start:end], BASE+start):
        m=ins.mnemonic; b=m.split('.')[0]; ops=ins.operands
        if b=='bl':
            tgt=ops[0].imm if ops and ops[0].type==ARM_OP_IMM else None
            if tgt==INIT:
                port=GPIO.get(reg.get('r0'))
                sb=sp_tag.get('r1')
                if port is not None and sb is not None:
                    inits.append((port, stack.get(sb),stack.get(sb+4),stack.get(sb+8),stack.get(sb+12),stack.get(sb+16), ins.address))
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
            elif b in('add','adds','add.w') and len(ops)==3 and ops[1].type==ARM_OP_REG and ins.reg_name(ops[1].reg)=='sp' and ops[2].type==ARM_OP_IMM:
                sp_tag[ins.reg_name(ops[0].reg)]=ops[2].imm; reg.pop(ins.reg_name(ops[0].reg),None)
            elif m.startswith('str') and ops[1].type==ARM_OP_MEM:
                mem=ops[1].mem; src=ins.reg_name(ops[0].reg); bse=ins.reg_name(mem.base) if mem.base else None
                if bse=='sp' and src in reg: stack[mem.disp]=reg[src]
                elif bse in sp_tag and src in reg: stack[sp_tag[bse]+mem.disp]=reg[src]
            elif ops and ops[0].type==ARM_OP_REG:
                d=ins.reg_name(ops[0].reg); reg.pop(d,None); sp_tag.pop(d,None)
        except: pass
for s,e in funcs:
    if 4<e-s<6000: analyze(s,e)

AF={
 ('PA',9):'USART1_TX',('PA',10):'USART1_RX',('PA',8):'(GPIO/TIM1_CH1)',
 ('PA',5):'SPI1_SCK?',('PA',6):'SPI1_MISO?',('PA',7):'SPI1_MOSI?',
 ('PC',6):'USART6_TX/TIM3',('PC',7):'USART6_RX/TIM3',
}
MODE={0x0:'INPUT',0x1:'OUT_PP',0x11:'OUT_OD',0x2:'AF_PP',0x12:'AF_OD',0x3:'ANALOG'}
PULL={0:'',1:'PU',2:'PD',None:'?'}
print(f"=== HAL_GPIO_Init call sites decoded: {len(inits)} ===")
rows={}
for port,pinm,mode,pull,spd,alt,addr in inits:
    if pinm is None or mode is None: continue
    for p in range(16):
        if (pinm>>p)&1:
            ml=mode&0xFFFF; exti=(mode>>16)
            if exti:
                lab={0x1011:'IT_RISING',0x1021:'IT_FALLING',0x1031:'IT_BOTH'}.get(mode>>16,'IT')
                lab='IN_'+lab
            else:
                lab=MODE.get(ml,f'm0x{ml:X}')
            sig=''
            if ml in(0x2,0x12): sig=f"AF{alt}"
            rows[(port,p)]=(lab,PULL.get(pull,'?'),sig)
for (port,p) in sorted(rows,key=lambda k:(k[0],k[1])):
    lab,pull,sig=rows[(port,p)]
    extra=AF.get((port,p),'')
    print(f"   {port}{p:<2} {lab:<12} {pull:<3} {sig:<5} {extra}")
print(f"\ntotal distinct pins configured: {len(rows)}")
