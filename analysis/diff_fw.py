import struct,sys
BASE=0x08000000
A=open("stock_RTS-1_backup.bin","rb").read()
B=open(sys.argv[1],"rb").read()
def u32(d,o): return struct.unpack_from("<I",d,o)[0]
# differing byte ranges (coalesce runs within 64 bytes)
diffs=[i for i in range(min(len(A),len(B))) if A[i]!=B[i]]
print(f"total differing bytes: {len(diffs)} of {len(A)} ({100*len(diffs)/len(A):.1f}%)")
ranges=[]
if diffs:
    s=p=diffs[0]
    for d in diffs[1:]:
        if d-p>64: ranges.append((s,p)); s=d
        p=d
    ranges.append((s,p))
print(f"changed regions: {len(ranges)}")
for s,e in ranges[:40]:
    print(f"   0x{BASE+s:08X} .. 0x{BASE+e:08X}  ({e-s+1} bytes)")
print("\n== vector table compare (first 8 words) ==")
for k in range(8):
    a=u32(A,4*k); b=u32(B,4*k)
    print(f"   [{k}] old=0x{a:08X}  new=0x{b:08X} {'  <-- changed' if a!=b else ''}")
