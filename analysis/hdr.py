import struct,sys
BASE=0x08000000
A=open("stock_RTS-1_backup.bin","rb").read()
B=open(sys.argv[1],"rb").read()
def w(d,o): return struct.unpack_from("<I",d,o)[0]
def h(d,o): return struct.unpack_from("<H",d,o)[0]
print("== image header @0x0800C000 (old vs new) ==")
H=0xC000
for k in range(12):
    o=H+4*k; a=w(A,o); b=w(B,o)
    mark='  <-- CHANGED' if a!=b else ''
    print(f"  +0x{4*k:02X} (0x{BASE+o:08X}): old=0x{a:08X}  new=0x{b:08X}{mark}")
print("\n== interpret as halfwords around the changed version field (+0x0C) ==")
for o in (H+0x08,H+0x0C,H+0x10):
    print(f"  0x{BASE+o:08X}: old u16=({h(A,o)},{h(A,o+2)})  new u16=({h(B,o)},{h(B,o+2)})  old bytes={list(A[o:o+4])} new bytes={list(B[o:o+4])}")
