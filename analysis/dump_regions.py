import struct
IMG=open("stock_RTS-1_backup.bin","rb").read(); BASE=0x08000000
GPIO={0x40020000:"PA",0x40020400:"PB",0x40020800:"PC",0x40020C00:"PD",0x40021000:"PE",0x40021C00:"PH"}
def ann(w):
    if w in GPIO: return f"<{GPIO[w]} base>"
    if 0x08000000<=w<0x08040000: return f"<code/ptr 0x{w:08X}>"
    if w!=0 and (w&(w-1))==0 and w<=0x8000: return f"<pinmask bit{w.bit_length()-1}>"
    if 0x20000000<=w<0x20020000: return f"<RAM 0x{w:08X}>"
    return ""
def dump(start,end):
    print(f"\n==== 0x{start:08X} .. 0x{end:08X} ====")
    for a in range(start,end,16):
        o=a-BASE
        words=[struct.unpack_from('<I',IMG,o+k)[0] for k in range(0,16,4)]
        hexs=" ".join(f"{w:08X}" for w in words)
        anns=" ".join(f"{ann(w)}" for w in words if ann(w))
        print(f"  0x{a:08X}: {hexs}   {anns}")
dump(0x08019E20,0x08019EC0)
dump(0x080020E0,0x08002130)
dump(0x08001100,0x08001140)
