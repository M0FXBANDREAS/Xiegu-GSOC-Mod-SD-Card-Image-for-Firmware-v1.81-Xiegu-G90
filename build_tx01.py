"""Exact-input patch: B2 -> experimental TX01. Run with PYTHONPATH=deps."""
import struct,json,hashlib
from pathlib import Path
from keystone import Ks,KS_ARCH_ARM,KS_MODE_ARM
p=Path(__file__).parent;b=bytearray((p/'app-b2.bin').read_bytes());original=bytes(b)
expected=json.loads((p/'runtime-brand-manifest.json').read_text())['branded_sha256']
assert hashlib.sha256(b).hexdigest()==expected,'Unexpected B2 executable'
k=Ks(KS_ARCH_ARM,KS_MODE_ARM);changes=[]
ph=struct.unpack_from('<I',b,28)[0]+6*32;off=struct.unpack_from('<I',b,ph+4)[0];assert off==0x146000
b.extend(bytes(off+0xc00-len(b)))
def put(addr,data,why):
 pos=addr-0x140000+off if addr>=0x140000 else addr-0x10000
 before=bytes(b[pos:pos+len(data)]);b[pos:pos+len(data)]=data
 changes.append({'address':hex(addr),'before':before.hex(),'after':data.hex(),'reason':why})
def asm(s,a):return bytes(k.asm(s,addr=a)[0])
# Stock PTT (byte36 bit7) and tune (byte37 bit5) now pass through unchanged.
# Keep VOX suppressed, operate active, and AUTO FFT scales from the tested RX build.
guard='''
push {r4,lr}
bl 0x1fc64
mov r4,r0
ldrb r1,[r4,#38]
bic r1,r1,#8
orr r1,r1,#2
strb r1,[r4,#38]
ldrb r1,[r4,#19]
bic r1,r1,#15
orr r1,r1,#1
strb r1,[r4,#19]
ldrb r1,[r4,#35]
bic r1,r1,#15
orr r1,r1,#1
strb r1,[r4,#35]
mov r0,r4
pop {r4,pc}
'''
g=asm(guard,0x140000);assert len(g)<0x100;put(0x140000,g+bytes(0x100-len(g)),'Preserve stock PTT and ATU request/release; VOX remains disabled')
# Reuse existing native Qt branding wrapper; same QLabel, new geometry and string.
old_source=(p/'add_runtime_brand.py').read_text();code=old_source.split("code='''",1)[1].split("'''",1)[0]
code=code.replace('movw r0,#906','movw r0,#275').replace('mov r0,#6','mov r0,#7').replace('movw r0,#1020','movw r0,#479').replace('mov r0,#38','mov r0,#43')
put(0x140200,asm(code,0x140200),'Branding placed in header gap x275..479 before FILTER x490')
put(0x140400,b'M0FXB HamTech Mod\0'+bytes(64-17),'Exact running branding text')
style=b'color: #49dff3; font-size: 18px; font-weight: bold; background: transparent;\0'
assert len(style)<0x100;put(0x140440,style,'Readable cyan header branding')
assert b[0x2d7d8-0x10000:0x2d7dc-0x10000]==asm('mov sl,#480',0x2d7d8)
put(0x2d7d8,asm('movw sl,#265',0x2d7d8),'Reserve branding gap by limiting channel label to x130..265')
# Replace only the color table constructor. FFT values, timing and scaling are unchanged.
constructor=asm('''push {r4,lr}
movw r1,#0x800
movt r1,#0x14
mov r2,#1024
bl 0x1fc64
pop {r4,pc}''',0x140600)
put(0x140600,constructor,'Install custom 256-entry blue waterfall palette')
assert b[0x39020-0x10000:0x39024-0x10000]==asm('vmov.f64 d22,#0.5',0x39020)
put(0x39020,asm('b 0x140600',0x39020),'Redirect XColorMap constructor to blue palette; stock lookup retained')
anchors=[(0,(0,0,8)),(64,(0,8,52)),(128,(0,55,170)),(176,(0,145,255)),(208,(50,235,255)),(232,(255,235,64)),(255,(255,60,16))]
colors=[]
for i in range(256):
 lo,hi=next((a,z) for a,z in zip(anchors,anchors[1:]) if a[0]<=i<=z[0]);f=(i-lo[0])/(hi[0]-lo[0]);rgb=tuple(round(a+(z-a)*f) for a,z in zip(lo[1],hi[1]));colors.append((rgb[0]<<16)|(rgb[1]<<8)|rgb[2])
put(0x140800,struct.pack('<256I',*colors),'Dark navy/blue/cyan palette with yellow/red strong signals')
struct.pack_into('<II',b,ph+16,0xc00,0xc00)
(p/'gsoc_app_v1').write_bytes(b)
# Prove all original bytes outside the small, explicitly listed ranges are untouched.
allowed=[(0x2d7d8-0x10000,0x2d7dc-0x10000),(0x39020-0x10000,0x39024-0x10000),(ph+16,ph+24),(off,off+0x100),(off+0x200,off+0x200+len(asm(code,0x140200))),(off+0x400,off+0x500)]
for i in range(len(original)):
 if original[i]!=b[i]:assert any(a<=i<z for a,z in allowed),hex(i)
manifest={'build':'HamTech V1.4beta TX01','target_radio':'G90 MainUnit V1.81','input_b2_sha256':expected,'output_sha256':hashlib.sha256(b).hexdigest(),'branding':{'text':'M0FXB HamTech Mod','rectangle':[275,7,205,37],'font_px':18},'palette_anchors':anchors,'patches':changes,'retained':['1.81 six-mode mapping','1.81 float-edge filter encoding','AUTO FFT scale','stock CRC and serial transport','stock PTT and ATU UI/state machines'],'limitations':['Hardware untested','No guarantee of complete G90 1.81 compatibility','VOX requests remain disabled','No U-D/L-D UI modes','No claimed waterfall speed change']}
(p/'TX01-patch-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Patched TX01 application:',manifest['output_sha256'])
