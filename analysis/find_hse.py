import struct,sys
d=open(sys.argv[1],'rb').read(); BASE=0x08000000
# Scan for STM32F4 RCC_PLLCFGR-looking constants and decode HSE.
# PLLCFGR: PLLM[5:0], PLLN[14:6], PLLP[17:16], PLLSRC[22], PLLQ[27:24]
cands=[]
for o in range(0,len(d)-3,2):  # 2-byte step (movw/movt or literal)
    w=struct.unpack_from('<I',d,o)[0]
    pllm=w&0x3F; plln=(w>>6)&0x1FF; pllp=((w>>16)&3); pllsrc=(w>>22)&1; pllq=(w>>24)&0xF
    rsvd=(w>>28)&0xF
    if rsvd==0 and pllsrc==1 and 2<=pllm<=63 and 50<=plln<=432 and 2<=pllq<=15:
        p=(pllp+1)*2
        vco_for_usb = 48*pllq            # USB needs 48MHz from VCO/PLLQ
        hse = pllm*vco_for_usb/plln if plln else 0
        sysclk = vco_for_usb/p
        if 4<=hse<=26 and 24<=sysclk<=84.0001:
            cands.append((o,w,pllm,plln,p,pllq,pllsrc,hse,sysclk))
seen=set(); 
print("offset      value       PLLM PLLN PLLP PLLQ SRC   HSE(MHz)  SYSCLK")
for o,w,m,n,p,q,s,hse,sys_ in cands:
    key=(w)
    if key in seen: continue
    seen.add(key)
    print(f"0x{BASE+o:08X}  0x{w:08X}  {m:>4} {n:>4} {p:>4} {q:>4} HSE   {hse:>7.3f}   {sys_:.1f}")
if not cands:
    print("No HSE-sourced PLLCFGR found -> may run PLL off HSI (internal). Checking HSI-source candidates...")
    for o in range(0,len(d)-3,2):
        w=struct.unpack_from('<I',d,o)[0]
        if ((w>>22)&1)==0 and (w&0x3F)==16 and 50<=((w>>6)&0x1FF)<=432 and ((w>>28)&0xF)==0 and 2<=((w>>24)&0xF)<=15:
            print(f"  HSI cand @0x{BASE+o:08X}: 0x{w:08X} PLLM=16 PLLN={(w>>6)&0x1FF}")
            break
