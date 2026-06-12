import struct, sys
from capstone import *
from capstone.arm import *
IMG=open(sys.argv[1],"rb").read(); BASE=0x08000000
def rd32(a):
    o=a-BASE; return struct.unpack_from("<I",IMG,o)[0] if 0<=o<=len(IMG)-4 else None
GPIO={0x40020000:"PA",0x40020400:"PB",0x40020800:"PC",0x40020C00:"PD",0x40021000:"PE"}
WRITEPIN=0x08019EC4; INIT=0x08019B48
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB); md.detail=True
def pins(mask): return [f"{p}" for p in range(16) if (mask>>p)&1]

start=0x08012C24; end=0x080131C4
reg={}; sp_tag={}; stack={}; dreg={}
print("=== trace of motion-init @0x08012C24: GPIO_Init + WritePin actions in order ===")
for ins in md.disasm(IMG[start-BASE:end-BASE], start):
    m=ins.mnemonic;b=m.split('.')[0];ops=ins.operands
    if b=='bl':
        tgt=ops[0].imm if ops and ops[0].type==ARM_OP_IMM else None
        port=GPIO.get(reg.get('r0'))
        if tgt==WRITEPIN and port is not None:
            pm=reg.get('r1'); st=reg.get('r2')
            bits=pins(pm) if isinstance(pm,int) else '?'
            print(f"  0x{ins.address:08X} WritePin {port} pins{bits} = {st}")
        elif tgt==INIT and port is not None and 'r1' in sp_tag:
            sb=sp_tag['r1']; pm=stack.get(sb); mode=stack.get(sb+4); alt=stack.get(sb+16)
            ml=(mode&0xFFFF) if mode is not None else None
            lab={0:'IN',1:'OUT',0x11:'OUT_OD',2:'AF',0x12:'AF_OD',3:'ANALOG'}.get(ml,hex(ml) if ml is not None else '?')
            ex='/EXTI' if (mode and mode>>16) else ''
            print(f"  0x{ins.address:08X} GPIO_Init {port} pins{pins(pm) if isinstance(pm,int) else '?'} mode={lab}{ex} af={alt}")
        for r in('r0','r1','r2','r3','r12'): reg.pop(r,None); sp_tag.pop(r,None)
        continue
    if b in('b','bx','blx','cbz','cbnz'): continue
    try:
        if m.startswith('vldr') and ops[1].mem.base==ARM_REG_PC:
            a=((ins.address+4)&~3)+ops[1].mem.disp; dreg[ins.reg_name(ops[0].reg)]=(rd32(a),rd32(a+4))
        elif m.startswith('vstr'):
            d=ins.reg_name(ops[0].reg);mem=ops[1].mem;bse=ins.reg_name(mem.base) if mem.base else None
            if d in dreg:
                lo,hi=dreg[d]
                if bse=='sp': stack[mem.disp]=lo;stack[mem.disp+4]=hi
                elif bse in sp_tag: stack[sp_tag[bse]+mem.disp]=lo;stack[sp_tag[bse]+mem.disp+4]=hi
        elif m=='strd':
            ra=ins.reg_name(ops[0].reg);rb=ins.reg_name(ops[1].reg);mem=ops[2].mem
            bse=ins.reg_name(mem.base) if mem.base else None;bo=None
            if bse=='sp':bo=mem.disp
            elif bse in sp_tag:bo=sp_tag[bse]+mem.disp
            if bo is not None: stack[bo]=reg.get(ra);stack[bo+4]=reg.get(rb)
        elif m.startswith('ldr') and ops[1].type==ARM_OP_MEM and ops[1].mem.base==ARM_REG_PC:
            d=ins.reg_name(ops[0].reg);v=rd32(((ins.address+4)&~3)+ops[1].mem.disp)
            if v is not None: reg[d]=v; sp_tag.pop(d,None)
            else: reg.pop(d,None)
        elif m=='movw': reg[ins.reg_name(ops[0].reg)]=ops[1].imm&0xFFFF;sp_tag.pop(ins.reg_name(ops[0].reg),None)
        elif m=='movt':
            d=ins.reg_name(ops[0].reg);reg[d]=(reg.get(d,0)&0xFFFF)|((ops[1].imm&0xFFFF)<<16)
        elif m in('mov','movs','mov.w') and ops[1].type==ARM_OP_IMM:
            reg[ins.reg_name(ops[0].reg)]=ops[1].imm&0xFFFFFFFF;sp_tag.pop(ins.reg_name(ops[0].reg),None)
        elif m in('mov','mov.w') and ops[1].type==ARM_OP_REG:
            s=ins.reg_name(ops[1].reg);d=ins.reg_name(ops[0].reg)
            if s=='sp': sp_tag[d]=0;reg.pop(d,None)
            elif s in reg: reg[d]=reg[s];sp_tag.pop(d,None)
            else: reg.pop(d,None);sp_tag.pop(d,None)
        elif b in('add','adds','add.w') and len(ops)==3 and ops[1].type==ARM_OP_REG and ins.reg_name(ops[1].reg)=='sp':
            sp_tag[ins.reg_name(ops[0].reg)]=ops[2].imm;reg.pop(ins.reg_name(ops[0].reg),None)
        elif m.startswith('str') and len(ops)==2 and ops[1].type==ARM_OP_MEM:
            mem=ops[1].mem;src=ins.reg_name(ops[0].reg);bse=ins.reg_name(mem.base) if mem.base else None
            if bse=='sp' and src in reg: stack[mem.disp]=reg[src]
            elif bse in sp_tag and src in reg: stack[sp_tag[bse]+mem.disp]=reg[src]
        elif ops and ops[0].type==ARM_OP_REG and m not in('cmp','tst','cmn'):
            d=ins.reg_name(ops[0].reg);reg.pop(d,None);sp_tag.pop(d,None)
    except: pass
