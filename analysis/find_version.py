import struct
IMG=open("stock_RTS-1_backup.bin","rb").read(); BASE=0x08000000
def u32(o): return struct.unpack_from("<I",IMG,o)[0]
# STM32F401RC sector starts
sectors=[0x0000,0x4000,0x8000,0xC000,0x10000,0x20000]
print("== scan sector boundaries for a 2nd vector table (app start) ==")
app=None
for s in sectors:
    sp=u32(s); rv=u32(s+4)
    vt = (0x20000000<=sp<=0x20010000) and (BASE<=rv<BASE+0x40000) and (rv&1)
    tag = " <-- looks like vector table" if vt else ""
    print(f"  0x{BASE+s:08X}: SP=0x{sp:08X} reset=0x{rv:08X}{tag}")
    if vt and s!=0 and app is None: app=s

# Look for image header magic / version near app start or bootloader. Dump a few candidate header regions.
print("\n== dump first 0x40 bytes of each sector (look for magic/version struct) ==")
for s in sectors:
    words=[u32(s+4*k) for k in range(16)]
    print(f"  @0x{BASE+s:08X}: "+" ".join(f"{w:08X}" for w in words[:8]))
    print(f"               "+" ".join(f"{w:08X}" for w in words[8:]))

# search for 'RTS1BOOT' magic occurrences and dump surrounding 32 bytes (header likely near it)
needle=b"RTS1BOOT"
i=IMG.find(needle)
while i!=-1:
    print(f"\n== 'RTS1BOOT' @0x{BASE+i:08X}; surrounding words ==")
    base=(i-16)&~3
    for k in range(0,12):
        o=base+4*k
        print(f"   0x{BASE+o:08X}: {u32(o):08X}")
    i=IMG.find(needle,i+1)
