import struct,sys
from capstone import *
from capstone.arm import *
IMG=open(sys.argv[1],'rb').read(); BASE=0x08000000
def rd32(a):
    o=a-BASE; return struct.unpack_from('<I',IMG,o)[0] if 0<=o<=len(IMG)-4 else None
GPIO={0x40020000:"PA",0x40020400:"PB",0x40020800:"PC",0x40020C00:"PD",0x40021000:"PE"}
WRITEPIN=0x08019EC4; READPIN=0x08019EB8
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB); md.detail=True

def find_str(s):
    i=IMG.find(s.encode()); return BASE+i if i>=0 else None

# For a task: find where its name-string address is loaded as a literal; the task
# function pointer is usually an adjacent literal in the same pool.
def task_func(name):
    saddr=find_str(name)
    if not saddr: return None,None
    # scan literal pool words for saddr, then look at neighbors for a code ptr (odd, in flash)
    for o in range(0,len(IMG)-3,4):
        if struct.unpack_from('<I',IMG,o)[0]==saddr:
            for d in (-8,-4,4,8,-12,12):
                v=rd32(BASE+o+d)
                if v and (v&1) and 0x08000000<=v<0x08040000:
                    return saddr, v&~1
    return saddr,None

def pins_driven(faddr,maxn=400):
    """scan a function body for WritePin/ReadPin (port,pin,state)."""
    reg={}; outs=[]; ins_=[]
    o=faddr-BASE
    for k,i in enumerate(md.disasm(IMG[o:o+maxn*2], faddr)):
        if k>maxn: break
        m=i.mnemonic;b=m.split('.')[0];ops=i.operands
        if b=='bl':
            tgt=ops[0].imm if ops and ops[0].type==ARM_OP_IMM else None
            port=GPIO.get(reg.get('r0'));pm=reg.get('r1');st=reg.get('r2')
            if tgt==WRITEPIN and port and pm and (pm&(pm-1))==0 and pm<=0x8000:
                outs.append((f"{port}{pm.bit_length()-1}",st))
            if tgt==READPIN and port and pm and (pm&(pm-1))==0 and pm<=0x8000:
                ins_.append(f"{port}{pm.bit_length()-1}")
            for r in('r0','r1','r2','r3','r12'): reg.pop(r,None)
            continue
        if b in('bx',) : break
        if b in('b','blx','cbz','cbnz'): continue
        try:
            if m.startswith('ldr') and ops[1].type==ARM_OP_MEM and ops[1].mem.base==ARM_REG_PC:
                d=i.reg_name(ops[0].reg);v=rd32(((i.address+4)&~3)+ops[1].mem.disp)
                reg[d]=v if v is not None else reg.pop(d,None)
                if v is not None: reg[d]=v
            elif m=='movw': reg[i.reg_name(ops[0].reg)]=ops[1].imm&0xFFFF
            elif m=='movt':
                d=i.reg_name(ops[0].reg);reg[d]=(reg.get(d,0)&0xFFFF)|((ops[1].imm&0xFFFF)<<16)
            elif m in('mov','movs','mov.w') and ops[1].type==ARM_OP_IMM:
                reg[i.reg_name(ops[0].reg)]=ops[1].imm&0xFFFFFFFF
            elif ops and ops[0].type==ARM_OP_REG and m not in('cmp','tst','cmn'):
                reg.pop(i.reg_name(ops[0].reg),None)
        except: pass
    return outs,ins_

for name in ["powerTask","SpindleTask","stepperTask"]:
    saddr,faddr=task_func(name)
    print(f"\n### {name}: name@{hex(saddr) if saddr else None}  func@{hex(faddr) if faddr else None}")
    if faddr:
        outs,ins_=pins_driven(faddr)
        # also follow: many task funcs are thin; report what we see
        print(f"   outputs written (pin=state): {outs[:12]}")
        print(f"   inputs read: {sorted(set(ins_))}")
