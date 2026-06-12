import struct
from capstone import *
IMG=open("stock_RTS-1_backup.bin","rb").read(); BASE=0x08000000
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB); md.detail=True
def dump(addr,n=28,label=""):
    o=addr-BASE
    print(f"\n===== func @0x{addr:08X} {label} =====")
    for ins in list(md.disasm(IMG[o:o+n*4], addr))[:n]:
        print(f"  0x{ins.address:08X}  {ins.mnemonic:9} {ins.op_str}")
dump(0x08019EC4,16,"(known WritePin)")
dump(0x08019EB8,10,"(known ReadPin)")
dump(0x08019B48,30,"(unknown A - 22 calls)")
dump(0x08001E0C,30,"(unknown B - 5 calls)")
dump(0x08002114,40,"(suspected GPIO_Init/MX)")
