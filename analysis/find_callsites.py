import struct
from capstone import *
from capstone.arm import *
IMG=open("stock_RTS-1_backup.bin","rb").read(); BASE=0x08000000
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB); md.detail=True
INIT=0x08019B48
ins_list=list(md.disasm(IMG,BASE))
idx={ins.address:i for i,ins in enumerate(ins_list)}
sites=[]
for ins in ins_list:
    if ins.mnemonic=='bl' and ins.operands and ins.operands[0].type==ARM_OP_IMM and ins.operands[0].imm==INIT:
        sites.append(ins.address)
print(f"call sites to HAL_GPIO_Init(0x{INIT:08X}): {len(sites)}")
for addr in sites[:3]:
    i=idx.get(addr)
    if i is None: continue
    print(f"\n--- context before call @0x{addr:08X} ---")
    for j in range(max(0,i-22),i+1):
        ii=ins_list[j]
        print(f"   0x{ii.address:08X}  {ii.mnemonic:9} {ii.op_str}")
