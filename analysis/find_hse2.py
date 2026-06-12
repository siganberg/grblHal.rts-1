import struct,sys
d=open(sys.argv[1],'rb').read(); BASE=0x08000000
xtals={8000000:"8MHz",12000000:"12MHz",16000000:"16MHz",24000000:"24MHz",
       25000000:"25MHz",26000000:"26MHz",20000000:"20MHz",27000000:"27MHz",
       48000000:"48MHz",10000000:"10MHz",14745600:"14.7456MHz"}
hits={}
for o in range(0,len(d)-3,4):
    w=struct.unpack_from('<I',d,o)[0]
    if w in xtals: hits.setdefault(w,[]).append(o)
# also unaligned
for o in range(0,len(d)-3,1):
    w=struct.unpack_from('<I',d,o)[0]
    if w in xtals and o%4: hits.setdefault(w,[]).append(o)
print("Standard crystal-frequency literals found:")
for w in sorted(hits):
    locs=sorted(set(hits[w]))
    print(f"  {xtals[w]:>12} (0x{w:08X}): {len(locs)} occurrence(s) @ {[hex(BASE+x) for x in locs[:6]]}")
if not hits: print("  none")
# Also: HSI fallback constant 16000000 is also HSI_VALUE; distinguish by context.
