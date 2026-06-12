import struct, collections, sys
from capstone import *
from capstone.arm import *
IMG=open(sys.argv[1],"rb").read(); BASE=0x08000000
def rd32(a):
    o=a-BASE; return struct.unpack_from("<I",IMG,o)[0] if 0<=o<=len(IMG)-4 else None
GPIO={0x40020000:"PA",0x40020400:"PB",0x40020800:"PC",0x40020C00:"PD",0x40021000:"PE"}
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB); md.detail=True

# ---- find HAL_GPIO_TogglePin: small func reading ODR(0x14) and writing BSRR(0x18) ----
starts=set()
for o in range(0,len(IMG)-1,2):
    hw=struct.unpack_from("<H",IMG,o)[0]
    if 0xB500<=hw<=0xB5FF: starts.add(o)
    if hw==0xE92D and (struct.unpack_from("<H",IMG,o+2)[0]&0x4000): starts.add(o)
starts=sorted(starts)
funcs=[(s,(starts[i+1] if i+1<len(starts) else len(IMG))) for i,s in enumerate(starts)]
# also scan tiny non-prologue funcs: toggle may be a leaf without push. Scan whole img for the idiom.
toggle_addr=None
ins_all=list(md.disasm(IMG,BASE))
for i,ins in enumerate(ins_all):
    if ins.mnemonic.startswith('ldr') and ins.op_str.endswith('[r0, #0x14]'):
        # look ahead a few for str [r0,#0x18]
        for j in range(i,min(i+8,len(ins_all))):
            if ins_all[j].mnemonic.startswith('str') and '[r0, #0x18]' in ins_all[j].op_str:
                toggle_addr=ins.address; break
        if toggle_addr: break
print(f"HAL_GPIO_TogglePin candidate @ {hex(toggle_addr) if toggle_addr else None}")

def scan_calls(target):
    res=collections.Counter()
    for s,e in funcs:
        if not(4<e-s<6000): continue
        reg={}
        for ins in md.disasm(IMG[s:e], BASE+s):
            m=ins.mnemonic;b=m.split('.')[0];ops=ins.operands
            if b=='bl':
                if ops and ops[0].type==ARM_OP_IMM and ops[0].imm==target:
                    port=GPIO.get(reg.get('r0')); pm=reg.get('r1')
                    if port and pm and (pm&(pm-1))==0 and pm<=0x8000:
                        res[(port,pm.bit_length()-1)]+=1
                for r in('r0','r1','r2','r3','r12'): reg.pop(r,None)
                continue
            if b in('b','bx','blx','cbz','cbnz'): continue
            try:
                if m.startswith('ldr') and ops[1].type==ARM_OP_MEM and ops[1].mem.base==ARM_REG_PC:
                    d=ins.reg_name(ops[0].reg); v=rd32(((ins.address+4)&~3)+ops[1].mem.disp)
                    if v is not None: reg[d]=v
                    else: reg.pop(d,None)
                elif m=='movw': reg[ins.reg_name(ops[0].reg)]=ops[1].imm&0xFFFF
                elif m=='movt':
                    d=ins.reg_name(ops[0].reg);reg[d]=(reg.get(d,0)&0xFFFF)|((ops[1].imm&0xFFFF)<<16)
                elif m in('mov','movs','mov.w') and ops[1].type==ARM_OP_IMM:
                    reg[ins.reg_name(ops[0].reg)]=ops[1].imm&0xFFFFFFFF
                elif ops and ops[0].type==ARM_OP_REG: reg.pop(ins.reg_name(ops[0].reg),None)
            except: pass
    return res

if toggle_addr:
    # find enclosing function start of toggle_addr to use as bl target
    tgt=toggle_addr
    # the real bl target is the function start; find largest start <= toggle_addr
    fs=[s for s in starts if BASE+s<=toggle_addr]
    tgt=BASE+max(fs) if fs else toggle_addr
    print(f"  -> using toggle func start 0x{tgt:08X}")
    tog=scan_calls(tgt)
    print("  TogglePin (port,pin) call sites  [= status LED / blinkers]:")
    for (p,pin),c in tog.most_common():
        print(f"     {p}{pin}: {c} calls")

# ---- default 'assigned_axis' values: search for a 5-byte/5-u32 default near settings ----
print("\n== search for plausible assigned_axis default [5] (values 0..3) near config ==")
# look for 5 consecutive small u32 in 0..3 range that look like axis assignment
for o in range(0,len(IMG)-20,4):
    v=[struct.unpack_from('<I',IMG,o+4*k)[0] for k in range(5)]
    if all(x<=3 for x in v) and len(set(v))>=3 and v.count(1)>=2:  # dual-Y => two 1's
        # heuristic: X=0,Y=1,Y=1,Z=2,A=3 pattern
        if v[0]==0 and v.count(1)==2:
            print(f"   @0x{BASE+o:08X}: {v}")
