import struct, collections
IMG=open("stock_RTS-1_backup.bin","rb").read(); BASE=0x08000000
GPIO={0x40020000:"PA",0x40020400:"PB",0x40020800:"PC",0x40020C00:"PD",0x40021000:"PE",0x40021C00:"PH"}
def ispow2(x): return x!=0 and (x&(x-1))==0
def pin_of_mask(m): return m.bit_length()-1 if ispow2(m) else None

# 1) where do GPIO base words occur?
locs=[]
for off in range(0,len(IMG)-3,4):
    w=struct.unpack_from("<I",IMG,off)[0]
    if w in GPIO: locs.append((off,w))
print(f"GPIO base words in image: {len(locs)}")

# 2) detect {port_base(4), pin_mask(2 or 4)} descriptor structs.
# try element strides 8 and 12 and 16; pin right after base as u16 or u32
def scan_struct(stride, pinoff, pinsize):
    found=[]
    for off,base in locs:
        if off+pinoff+pinsize<=len(IMG):
            pm = struct.unpack_from("<H" if pinsize==2 else "<I", IMG, off+pinoff)[0]
            p=pin_of_mask(pm)
            if p is not None and p<=15:
                found.append((off,GPIO[base],p,pm))
    return found

for stride in (8,12,16):
    for pinoff in (4,8):
        for pinsize in (2,4):
            res=scan_struct(stride,pinoff,pinsize)
            if len(res)>=6:
                print(f"\n-- candidate descriptor: pin as u{pinsize*8} at +{pinoff} ({len(res)} entries) --")
                for off,port,pin,pm in res:
                    print(f"   0x{BASE+off:08X}: {port}{pin}  (mask 0x{pm:04X})")
                break
