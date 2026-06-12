import struct,collections,sys
from capstone import *
from capstone.arm import *
IMG=open(sys.argv[1],'rb').read(); BASE=0x08000000
def rd32(a):
    o=a-BASE; return struct.unpack_from('<I',IMG,o)[0] if 0<=o<=len(IMG)-4 else None
GPIO={0x40020000:"PA",0x40020400:"PB",0x40020800:"PC",0x40020C00:"PD",0x40021000:"PE"}
WRITEPIN=0x08019EC4; READPIN=0x08019EB8
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB); md.detail=True
ins=list(md.disasm(IMG,BASE)); idx={i.address:k for k,i in enumerate(ins)}

# function starts
starts=sorted({o for o in range(0,len(IMG)-1,2)
    if 0xB500<=struct.unpack_from("<H",IMG,o)[0]<=0xB5FF
    or (struct.unpack_from("<H",IMG,o)[0]==0xE92D and struct.unpack_from("<H",IMG,o+2)[0]&0x4000)})
funcs=[(s,(starts[i+1] if i+1<len(starts) else len(IMG))) for i,s in enumerate(starts)]

# Find WritePin sites for target pins, with state and which input pins are read in the same function
targets={('PA',15),('PB',15),('PC',15)}
results=[]   # (port,pin,state,funcstart, reads_in_func)
for s,e in funcs:
    if not(4<e-s<6000): continue
    reg={}; wsites=[]; reads=set()
    for i in md.disasm(IMG[s:e], BASE+s):
        m=i.mnemonic;b=m.split('.')[0];ops=i.operands
        if b=='bl':
            tgt=ops[0].imm if ops and ops[0].type==ARM_OP_IMM else None
            port=GPIO.get(reg.get('r0')); pm=reg.get('r1'); st=reg.get('r2')
            if tgt==WRITEPIN and port and pm and (pm&(pm-1))==0 and pm<=0x8000:
                pin=pm.bit_length()-1
                if (port,pin) in targets: wsites.append((port,pin,st,i.address))
            if tgt==READPIN and port and pm and (pm&(pm-1))==0 and pm<=0x8000:
                reads.add(f"{port}{pm.bit_length()-1}")
            for r in('r0','r1','r2','r3','r12'): reg.pop(r,None)
            continue
        if b in('b','bx','blx','cbz','cbnz'): continue
        try:
            if m.startswith('ldr') and ops[1].type==ARM_OP_MEM and ops[1].mem.base==ARM_REG_PC:
                d=i.reg_name(ops[0].reg);v=rd32(((i.address+4)&~3)+ops[1].mem.disp)
                if v is not None: reg[d]=v
                else: reg.pop(d,None)
            elif m=='movw': reg[i.reg_name(ops[0].reg)]=ops[1].imm&0xFFFF
            elif m=='movt':
                d=i.reg_name(ops[0].reg);reg[d]=(reg.get(d,0)&0xFFFF)|((ops[1].imm&0xFFFF)<<16)
            elif m in('mov','movs','mov.w') and ops[1].type==ARM_OP_IMM:
                reg[i.reg_name(ops[0].reg)]=ops[1].imm&0xFFFFFFFF
            elif ops and ops[0].type==ARM_OP_REG and m not in('cmp','tst','cmn'):
                reg.pop(i.reg_name(ops[0].reg),None)
        except: pass
    for (port,pin,st,addr) in wsites:
        results.append((port,pin,st,s,sorted(reads)))

print("=== WritePin sites for PA15/PB15/PC15 (state, enclosing func, inputs read in same func) ===")
for port,pin,st,fs,reads in results:
    print(f"  {port}{pin} = {st}   in func @0x{BASE+fs:08X}   reads inputs: {reads}")
