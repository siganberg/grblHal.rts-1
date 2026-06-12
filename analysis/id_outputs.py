import struct,collections,sys
from capstone import *
from capstone.arm import *
IMG=open(sys.argv[1],'rb').read(); BASE=0x08000000
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB); md.detail=True
def disasm(addr,n,label):
    o=addr-BASE
    print(f"\n----- func @0x{addr:08X} {label} -----")
    for k,i in enumerate(md.disasm(IMG[o:o+n*4], addr)):
        if k>=n: break
        print(f"  0x{i.address:08X}  {i.mnemonic:9} {i.op_str}")

# find callers of a target address (bl target) via function-segmented scan
starts=sorted({o for o in range(0,len(IMG)-1,2)
    if 0xB500<=struct.unpack_from("<H",IMG,o)[0]<=0xB5FF
    or (struct.unpack_from("<H",IMG,o)[0]==0xE92D and struct.unpack_from("<H",IMG,o+2)[0]&0x4000)})
funcs=[(s,(starts[i+1] if i+1<len(starts) else len(IMG))) for i,s in enumerate(starts)]
def callers(target):
    out=[]
    for s,e in funcs:
        if not(4<e-s<8000): continue
        for i in md.disasm(IMG[s:e], BASE+s):
            if i.mnemonic=='bl' and i.operands and i.operands[0].type==ARM_OP_IMM and i.operands[0].imm==target:
                out.append((BASE+s,i.address))
    return out

for tgt,lbl in [(0x0800D7E4,"drives PC15 HIGH"),(0x0800DEE4,"drives PB15 HIGH")]:
    disasm(tgt,16,lbl)
    cs=callers(tgt)
    print(f"   called from {len(cs)} site(s): "+", ".join(f"0x{a:08X}(in fn 0x{f:08X})" for f,a in cs[:8]))

# strings near these funcs (sometimes a nearby literal points to a label)
print("\n=== nearby strings (fan/power/spindle/enable hints) ===")
import re
for m in re.finditer(rb'[ -~]{4,}', IMG):
    s=m.group().decode('latin-1')
    if any(k in s.lower() for k in ['fan','power','spindle','enable','estop','e-stop','stop','relay','vfd','cool','24v','48v','supply','motor power']):
        print(f"  0x{BASE+m.start():08X}: {s[:60]}")
