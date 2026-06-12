import struct, collections
from capstone import *
from capstone.arm import *
IMG=open("stock_RTS-1_backup.bin","rb").read(); BASE=0x08000000
def rd32(a):
    o=a-BASE; return struct.unpack_from("<I",IMG,o)[0] if 0<=o<=len(IMG)-4 else None
GPIO={0x40020000:"PA",0x40020400:"PB",0x40020800:"PC",0x40020C00:"PD",0x40021000:"PE",0x40021C00:"PH"}
USART1=0x40011000; USART6=0x40011400
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB); md.detail=True
WRITEPIN=0x08019EC4; READPIN=0x08019EB8

starts=set()
for o in range(0,len(IMG)-1,2):
    hw=struct.unpack_from("<H",IMG,o)[0]
    if 0xB500<=hw<=0xB5FF: starts.add(o)
    if hw==0xE92D and (struct.unpack_from("<H",IMG,o+2)[0]&0x4000): starts.add(o)
starts=sorted(starts)
funcs=[(s, (starts[i+1] if i+1<len(starts) else len(IMG))) for i,s in enumerate(starts)]

# characterize all GPIO-helper bl targets + collect pin args
helper_calls=collections.defaultdict(list)   # target -> list of (port,pinmask)
de_candidates=collections.Counter()          # (port,pin) written in funcs touching USART1
toggle_target=None

def scan(start,end, want_usart=False):
    reg={}; lits=set()
    wp_here=[]
    touches_usart=False
    for ins in md.disasm(IMG[start:end], BASE+start):
        m=ins.mnemonic; b=m.split('.')[0]; ops=ins.operands
        if b=='bl':
            tgt=ops[0].imm if ops and ops[0].type==ARM_OP_IMM else None
            port=GPIO.get(reg.get('r0')); pm=reg.get('r1')
            if tgt and port is not None:
                helper_calls[tgt].append((port,pm))
                if tgt==WRITEPIN and pm and (pm&(pm-1))==0 and pm<=0x8000:
                    wp_here.append((port,pm.bit_length()-1))
            for r in('r0','r1','r2','r3','r12'): reg.pop(r,None)
            continue
        if b in('b','bx','blx','cbz','cbnz'): continue
        try:
            if m.startswith('ldr') and ops[1].type==ARM_OP_MEM and ops[1].mem.base==ARM_REG_PC:
                d=ins.reg_name(ops[0].reg); v=rd32(((ins.address+4)&~3)+ops[1].mem.disp)
                if v is not None:
                    reg[d]=v
                    if v in (USART1,USART6) or (USART1<=v<USART1+0x20): touches_usart=True
                else: reg.pop(d,None)
            elif m=='movw': reg[ins.reg_name(ops[0].reg)]=ops[1].imm&0xFFFF
            elif m=='movt':
                d=ins.reg_name(ops[0].reg); reg[d]=(reg.get(d,0)&0xFFFF)|((ops[1].imm&0xFFFF)<<16)
                if reg[d] in (USART1,USART6): touches_usart=True
            elif m in('mov','movs','mov.w') and ops[1].type==ARM_OP_IMM:
                reg[ins.reg_name(ops[0].reg)]=ops[1].imm&0xFFFFFFFF
            elif ops and ops[0].type==ARM_OP_REG:
                reg.pop(ins.reg_name(ops[0].reg),None)
        except: pass
    if touches_usart:
        for pp in wp_here: de_candidates[pp]+=1
    return touches_usart, wp_here

for s,e in funcs:
    if 4<e-s<4000: scan(s,e)

print("=== GPIO-helper bl targets (r0=GPIO port) characterization ===")
for tgt,calls in sorted(helper_calls.items(), key=lambda x:-len(x[1]))[:8]:
    sb=[pm for _,pm in calls if pm and (pm&(pm-1))==0 and pm<=0x8000]
    role='WritePin' if tgt==WRITEPIN else 'ReadPin' if tgt==READPIN else '?'
    print(f"  0x{tgt:08X} [{role:8}] {len(calls)} calls, {len(set((p,(pm.bit_length()-1) if pm else None) for p,pm in calls if pm))} distinct pins")

print("\n=== RS-485 DE candidate: WritePin pins in functions that also touch USART1/6 ===")
for (port,pin),c in de_candidates.most_common(10):
    print(f"  {port}{pin}: seen in {c} USART-touching function(s)")

# STEP mask ordering: look for the 5 step masks appearing together
STEPMASK={0x0001:'PB0',0x0004:'PB2',0x0100:'PB8',0x0400:'PB10',0x2000:'PB13'}
print("\n=== Search for STEP-mask array (ordering => axis order X,Y1,Y2,Z,A) ===")
# scan data/code for sequences containing several step masks within a 64-byte window as u16 or u32
masks=set(STEPMASK)
for o in range(0,len(IMG)-2,2):
    w=struct.unpack_from("<H",IMG,o)[0]
    if w in masks:
        # gather a window of u16 values
        win=[struct.unpack_from("<H",IMG,o+2*k)[0] for k in range(0,8) if o+2*k+2<=len(IMG)]
        hits=[STEPMASK[x] for x in win if x in STEPMASK]
        if len(set(hits))>=3:
            print(f"  @0x{BASE+o:08X}: window u16 {[f'0x{x:04X}' for x in win]}  -> {hits}")
