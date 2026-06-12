import struct, collections
from capstone import *
from capstone.arm import *
IMG=open("stock_RTS-1_backup.bin","rb").read(); BASE=0x08000000
def rd32(a):
    o=a-BASE; return struct.unpack_from("<I",IMG,o)[0] if 0<=o<=len(IMG)-4 else None
GPIO={0x40020000:"PA",0x40020400:"PB",0x40020800:"PC",0x40020C00:"PD",0x40021000:"PE",0x40021C00:"PH"}
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB); md.detail=True
WRITEPIN=0x08019EC4; READPIN=0x08019EB8

starts=set()
for o in range(0,len(IMG)-1,2):
    hw=struct.unpack_from("<H",IMG,o)[0]
    if 0xB500<=hw<=0xB5FF: starts.add(o)
    if hw==0xE92D and (struct.unpack_from("<H",IMG,o+2)[0]&0x4000): starts.add(o)
starts=sorted(starts)

# (port,pin) -> {states seen}, site count, set of caller-func addrs
wp=collections.defaultdict(lambda:{'states':collections.Counter(),'sites':0,'funcs':set()})
rp=collections.Counter()
def analyze(start,end):
    reg={}
    for ins in md.disasm(IMG[start:end], BASE+start):
        m=ins.mnemonic; b=m.split('.')[0]; ops=ins.operands
        if b=='bl':
            tgt=ops[0].imm if ops and ops[0].type==ARM_OP_IMM else None
            port=GPIO.get(reg.get('r0')); pm=reg.get('r1'); st=reg.get('r2')
            if tgt==WRITEPIN and port and pm and (pm&(pm-1))==0 and pm<=0x8000:
                k=(port,pm.bit_length()-1); wp[k]['sites']+=1; wp[k]['funcs'].add(start)
                wp[k]['states'][st if st in (0,1) else '?']+=1
            if tgt==READPIN and port and pm and (pm&(pm-1))==0 and pm<=0x8000:
                rp[(port,pm.bit_length()-1)]+=1
            for r in('r0','r1','r2','r3','r12'): reg.pop(r,None)
            continue
        if b in('b','bx','blx','cbz','cbnz'): continue
        try:
            if m.startswith('ldr') and ops[1].type==ARM_OP_MEM and ops[1].mem.base==ARM_REG_PC:
                d=ins.reg_name(ops[0].reg); v=rd32(((ins.address+4)&~3)+ops[1].mem.disp)
                reg[d]=v if v is not None else reg.pop(d,None)
                if v is not None: reg[d]=v
            elif m=='movw': reg[ins.reg_name(ops[0].reg)]=ops[1].imm&0xFFFF
            elif m=='movt':
                d=ins.reg_name(ops[0].reg); reg[d]=(reg.get(d,0)&0xFFFF)|((ops[1].imm&0xFFFF)<<16)
            elif m in('mov','movs','mov.w') and ops[1].type==ARM_OP_IMM:
                reg[ins.reg_name(ops[0].reg)]=ops[1].imm&0xFFFFFFFF
            elif ops and ops[0].type==ARM_OP_REG:
                reg.pop(ins.reg_name(ops[0].reg),None)
        except: pass
for i,s in enumerate(starts):
    e=starts[i+1] if i+1<len(starts) else len(IMG)
    if 4<e-s<4000: analyze(s,e)

print("=== OUTPUT pins: state pattern (0/1/? = variable), #call-sites, #funcs ===")
print("   role hint: variable-state+manysites=DIR/control; constant=ENABLE/relay; 1 func toggled=LED/heartbeat")
for (port,pin) in sorted(wp):
    d=wp[(port,pin)]
    states=dict(d['states'])
    print(f"   {port}{pin:<2}: states={states}  sites={d['sites']}  funcs={len(d['funcs'])}")
print("\n=== INPUT pins: #read-sites (more reads ~ polled often) ===")
for (port,pin),c in sorted(rp.items()):
    print(f"   {port}{pin:<2}: reads={c}")
