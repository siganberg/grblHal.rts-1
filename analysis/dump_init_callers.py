import struct
from capstone import *
from capstone.arm import *
IMG=open("stock_RTS-1_backup.bin","rb").read(); BASE=0x08000000
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB); md.detail=True
INIT=0x08019B48
starts=set()
for o in range(0,len(IMG)-1,2):
    hw=struct.unpack_from("<H",IMG,o)[0]
    if 0xB500<=hw<=0xB5FF: starts.add(o)
    if hw==0xE92D and (struct.unpack_from("<H",IMG,o+2)[0]&0x4000): starts.add(o)
starts=sorted(starts)
funcs=[(s,(starts[i+1] if i+1<len(starts) else len(IMG))) for i,s in enumerate(starts)]

# find funcs that call INIT
callers=[]
for s,e in funcs:
    for ins in md.disasm(IMG[s:e], BASE+s):
        if ins.mnemonic=='bl' and ins.operands and ins.operands[0].type==ARM_OP_IMM and ins.operands[0].imm==INIT:
            callers.append((s,e)); break
print(f"functions calling HAL_GPIO_Init: {len(callers)}")
# dump the first 2 caller functions fully (trimmed)
for s,e in callers[:2]:
    print(f"\n===== caller func @0x{BASE+s:08X}..0x{BASE+e:08X} =====")
    for ins in md.disasm(IMG[s:e], BASE+s):
        print(f"   0x{ins.address:08X}  {ins.mnemonic:9} {ins.op_str}")
        if ins.address>=BASE+s+220: print("   ..."); break
