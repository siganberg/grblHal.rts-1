import struct, collections
from capstone import *
from capstone.arm import *
IMG=open("stock_RTS-1_backup.bin","rb").read(); BASE=0x08000000
def rd32(a):
    o=a-BASE; return struct.unpack_from("<I",IMG,o)[0] if 0<=o<=len(IMG)-4 else None
GPIO={0x40020000:"PA",0x40020400:"PB",0x40020800:"PC",0x40020C00:"PD",0x40021000:"PE",0x40021C00:"PH"}
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB); md.detail=True
ins_list=list(md.disasm(IMG,BASE))
idx={ins.address:i for i,ins in enumerate(ins_list)}

# simple: track r0 via ldr literal / mov; at each bl, if r0 is GPIO base, record target
reg={}
calls=collections.defaultdict(list)
for ins in ins_list:
    m=ins.mnemonic; b=m.split('.')[0]; ops=ins.operands
    if b=='bl':
        if ops and ops[0].type==ARM_OP_IMM and reg.get('r0') in GPIO:
            calls[ops[0].imm].append((ins.address,GPIO[reg['r0']]))
        reg.pop('r0',None);reg.pop('r1',None);reg.pop('r2',None);reg.pop('r3',None)
        continue
    if b in('b','bx','blx'): reg.clear(); continue
    try:
        if m.startswith('ldr') and ops[1].type==ARM_OP_MEM and ops[1].mem.base==ARM_REG_PC:
            v=rd32(((ins.address+4)&~3)+ops[1].mem.disp); d=ins.reg_name(ops[0].reg)
            if v is not None: reg[d]=v
            else: reg.pop(d,None)
        elif m in('mov','movs','mov.w') and ops[1].type==ARM_OP_IMM:
            reg[ins.reg_name(ops[0].reg)]=ops[1].imm
    except: pass

print("bl targets called with r0=GPIO base (top 6):")
for tgt,sites in sorted(calls.items(),key=lambda x:-len(x[1]))[:6]:
    ports=collections.Counter(p for _,p in sites)
    print(f"  0x{tgt:08X}: {len(sites)} calls  ports={dict(ports)}")

# Dump disasm around the first few call sites of the dominant target
if calls:
    top=max(calls,key=lambda t:len(calls[t]))
    print(f"\n--- context for 3 call sites of dominant target 0x{top:08X} (HAL_GPIO_Init?) ---")
    for addr,port in calls[top][:3]:
        i=idx[addr]
        print(f"\n  call @0x{addr:08X} port={port}:")
        for j in range(max(0,i-12),i+1):
            ii=ins_list[j]
            print(f"    0x{ii.address:08X}  {ii.mnemonic:8} {ii.op_str}")
