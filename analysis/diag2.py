import struct, collections
from capstone import *
from capstone.arm import *
IMG=open("stock_RTS-1_backup.bin","rb").read(); BASE=0x08000000
def rd32(a):
    o=a-BASE; return struct.unpack_from("<I",IMG,o)[0] if 0<=o<=len(IMG)-4 else None
GPIO={0x40020000:"PA",0x40020400:"PB",0x40020800:"PC",0x40020C00:"PD",0x40021000:"PE",0x40021C00:"PH"}
GREG={0:"MODER",4:"OTYPER",8:"OSPEEDR",0xC:"PUPDR",0x10:"IDR",0x14:"ODR",0x18:"BSRR",0x20:"AFRL",0x24:"AFRH"}
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB); md.detail=True
ins_list=list(md.disasm(IMG,BASE))

# Find ldr rX,[pc] that loads a GPIO base; show next 6 insns
hits=0
shown=collections.Counter()
for i,ins in enumerate(ins_list):
    if ins.mnemonic.startswith('ldr') and ins.operands and ins.operands[-1].type==ARM_OP_MEM and ins.operands[-1].mem.base==ARM_REG_PC:
        v=rd32(((ins.address+4)&~3)+ins.operands[-1].mem.disp)
        if v in GPIO and shown[GPIO[v]]<2:
            shown[GPIO[v]]+=1; hits+=1
            rd=ins.reg_name(ins.operands[0].reg)
            print(f"\n[{GPIO[v]} base -> {rd}] @0x{ins.address:08X}")
            for j in range(i,min(len(ins_list),i+7)):
                ii=ins_list[j]; print(f"   0x{ii.address:08X}  {ii.mnemonic:9} {ii.op_str}")
        if hits>=12: break

# Also: count GPIO register offsets actually accessed via str/ldr [base,#off] where base = recently loaded GPIO reg
print("\n=== GPIO register-offset access frequency (str/ldr [gpio,#off]) ===")
reg={}
offcnt=collections.Counter()  # (port,reg) -> count, plus access type
bsrr_imm=collections.Counter()
for ins in ins_list:
    m=ins.mnemonic; b=m.split('.')[0]; ops=ins.operands
    if b in('b','bl','bx','blx','cbz','cbnz'): 
        # keep r4-r11 maybe; simple: clear caller regs only on bl
        if b=='bl':
            for r in('r0','r1','r2','r3','r12'): reg.pop(r,None)
        else: reg.clear()
        continue
    try:
        if m.startswith('ldr') and ops[1].type==ARM_OP_MEM and ops[1].mem.base==ARM_REG_PC:
            v=rd32(((ins.address+4)&~3)+ops[1].mem.disp); d=ins.reg_name(ops[0].reg)
            if v is not None: reg[d]=v
            else: reg.pop(d,None)
        elif (m.startswith('str') or m.startswith('ldr')) and ops[-1].type==ARM_OP_MEM and ops[-1].mem.base!=ARM_REG_PC:
            mem=ops[-1].mem; base=ins.reg_name(mem.base) if mem.base else None
            if base in reg and reg[base] in GPIO and mem.index==0:
                port=GPIO[reg[base]]; off=mem.disp
                rn=GREG.get(off,f"+0x{off:X}")
                offcnt[(port,rn)]+=1
        elif m in('movw',): reg[ins.reg_name(ops[0].reg)]=ops[1].imm&0xFFFF
        elif m=='movt':
            d=ins.reg_name(ops[0].reg); reg[d]=(reg.get(d,0)&0xFFFF)|((ops[1].imm&0xFFFF)<<16)
        elif m in('mov','movs','mov.w') and ops[1].type==ARM_OP_IMM:
            reg[ins.reg_name(ops[0].reg)]=ops[1].imm
        elif ins.reg_name(ops[0].reg) in reg:
            reg.pop(ins.reg_name(ops[0].reg),None)
    except: pass
for (port,rn),c in sorted(offcnt.items(),key=lambda x:(-x[1]))[:30]:
    print(f"   {port} {rn:8} : {c}")
