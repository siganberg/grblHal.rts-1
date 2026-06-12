import struct, collections
from capstone import *
from capstone.arm import *
IMG=open("stock_RTS-1_backup.bin","rb").read(); BASE=0x08000000
def rd32(a):
    o=a-BASE; return struct.unpack_from("<I",IMG,o)[0] if 0<=o<=len(IMG)-4 else None
GPIO={0x40020000:"PA",0x40020400:"PB",0x40020800:"PC",0x40020C00:"PD",0x40021000:"PE",0x40021C00:"PH"}
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB); md.detail=True

# function starts: 16-bit push {..,lr}=0xB5xx ; 32-bit push.w {..,lr}=0xE92D ....
starts=set()
for o in range(0,len(IMG)-1,2):
    hw=struct.unpack_from("<H",IMG,o)[0]
    if 0xB500<=hw<=0xB5FF: starts.add(o)
    if hw==0xE92D and struct.unpack_from("<H",IMG,o+2)[0] & 0x4000: starts.add(o)
starts=sorted(starts)

writepin=[]   # (target,port,pinmask)  candidate WritePin/ReadPin/Init
allcalls=collections.Counter()
def analyze(start,end):
    reg={}
    code=IMG[start:end]
    for ins in md.disasm(code, BASE+start):
        m=ins.mnemonic; b=m.split('.')[0]; ops=ins.operands
        if b=='bl':
            if ops and ops[0].type==ARM_OP_IMM:
                tgt=ops[0].imm
                if reg.get('r0') in GPIO:
                    allcalls[tgt]+=1
                    writepin.append((tgt, GPIO[reg['r0']], reg.get('r1')))
            for r in('r0','r1','r2','r3','r12'): reg.pop(r,None)
            continue
        if b in('b','bx','blx','cbz','cbnz'): 
            # don't fully clear; conditional branches inside func - keep regs (best effort)
            continue
        try:
            if m.startswith('ldr') and ops[1].type==ARM_OP_MEM and ops[1].mem.base==ARM_REG_PC:
                d=ins.reg_name(ops[0].reg); v=rd32(((ins.address+4)&~3)+ops[1].mem.disp)
                if v is not None: reg[d]=v
                else: reg.pop(d,None)
            elif m=='movw': reg[ins.reg_name(ops[0].reg)]=ops[1].imm&0xFFFF
            elif m=='movt':
                d=ins.reg_name(ops[0].reg); reg[d]=(reg.get(d,0)&0xFFFF)|((ops[1].imm&0xFFFF)<<16)
            elif m in('mov','movs','mov.w') and ops[1].type==ARM_OP_IMM:
                reg[ins.reg_name(ops[0].reg)]=ops[1].imm&0xFFFFFFFF
            elif m in('mov','mov.w') and ops[1].type==ARM_OP_REG:
                s=ins.reg_name(ops[1].reg);d=ins.reg_name(ops[0].reg)
                if s in reg: reg[d]=reg[s]
                else: reg.pop(d,None)
            elif ops and ops[0].type==ARM_OP_REG:
                reg.pop(ins.reg_name(ops[0].reg),None)
        except: pass

for i,s in enumerate(starts):
    e = starts[i+1] if i+1<len(starts) else len(IMG)
    if e-s>4 and e-s<4000: analyze(s,e)

print("=== bl targets called with r0=GPIO port (likely HAL_GPIO_WritePin/ReadPin/Init) ===")
for tgt,c in allcalls.most_common(8):
    # pin immediates seen for this target
    pins=collections.Counter()
    for t,port,pm in writepin:
        if t==tgt and pm is not None and pm!=0 and (pm&(pm-1))==0 and pm<=0x8000:
            pins[(port,pm.bit_length()-1)]+=1
    print(f"  0x{tgt:08X}: {c} calls, distinct (port,pin) immediates: {len(pins)}")

# The HAL_GPIO functions: aggregate all (port,pin) with valid single-bit pin masks across the top 3 targets
top=[t for t,_ in allcalls.most_common(4)]
io=collections.defaultdict(set)
for t,port,pm in writepin:
    if t in top and pm is not None and pm!=0 and (pm&(pm-1))==0 and pm<=0x8000:
        io[port].add(pm.bit_length()-1)
print("\n=== ALL (port,pin) touched via GPIO helper calls (the active I/O pins) ===")
total=0
for port in sorted(io):
    pl=sorted(io[port]); total+=len(pl)
    print(f"  {port}: {pl}")
print(f"  total distinct pins: {total}")
