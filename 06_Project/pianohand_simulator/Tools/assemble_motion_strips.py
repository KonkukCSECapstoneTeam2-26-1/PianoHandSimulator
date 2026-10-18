"""Filmstrips + GIFs from the mo_* frames and the reference frames."""
import glob, os
from PIL import Image, ImageDraw
S='/private/tmp/claude-501/-Users-nunsori-Git-PianoHandSimulator/9a6accd9-1ec0-4f5a-a0d5-cb821657229a/scratchpad'
P='/Users/nunsori/Git/PianoHandSimulator/06_Project/pianohand_simulator/Saved/Screenshots/MacEditor/'
D='/Users/nunsori/Git/PianoHandSimulator/06_Project/pianohand_simulator/Docs/images/'
def ld(n): return Image.open(P+n+'.png').convert('RGB')
def label(im, txt):
    d=ImageDraw.Draw(im); d.rectangle((0,0,len(txt)*7+8,16),fill=(0,0,0)); d.text((4,2),txt,fill=(255,255,255)); return im
def strip(frames, cols, path, cell_w):
    rows=(len(frames)+cols-1)//cols; h=int(frames[0].size[1]*cell_w/frames[0].size[0])
    g=Image.new('RGB',(cols*(cell_w+4),rows*(h+4)),(16,16,16))
    for i,f in enumerate(frames): g.paste(f.resize((cell_w,h)),((i%cols)*(cell_w+4),(i//cols)*(h+4)))
    g.save(path,quality=88); print(path, g.size)
# (a) ref-view filmstrip: 12 of 48 frames
fr=[label(ld('mo2_ref_%02d'%i),'t=%.2f'%(i*4/48)) for i in range(0,48,4)]
strip(fr,6,D+'skin_v7_motion_refview_strip.jpg',420)
# (b) PIP close-up 16 frames
fr=[label(ld('mo_pip_%02d'%i),'t=%.2f'%(i*4/16)) for i in range(16)]
strip(fr,4,D+'skin_v7_motion_pip_strip.jpg',600)
# (c) dorsal 16 frames
fr=[label(ld('mo_dor_%02d'%i),'t=%.2f'%(i*4/16)) for i in range(16)]
strip(fr,4,D+'skin_v7_motion_dorsal_strip.jpg',480)
# (d) reference vs ours, phase matched: ref 241.0..244.0 <-> ours 0.25..1.6, ref 244.5..246.0 <-> ours 1.6..2.55
refs=sorted(glob.glob(S+'/ref_frames/ref_*.png'))
pairs=[]
for k,rp in enumerate(refs):
    t_ref=241.0+k*0.5
    t_our = 0.25+(t_ref-241.0)/3.0*(1.6-0.25) if t_ref<=244.0 else 1.6+(t_ref-244.5)/1.5*(2.55-1.6)
    i=int(round(t_our*12)); pairs.append((rp,t_ref,i,t_our))
cw=440; ch=int(432*cw/728); rows=[]
g=Image.new('RGB',(len(pairs)*(cw+4), 2*(ch+4)),(16,16,16))
for c,(rp,tr,i,to) in enumerate(pairs):
    r=Image.open(rp).convert('RGB').crop((0,0,728,385)).resize((cw,ch)); label(r,'ref %.1fs'%tr)
    o=ld('mo2_ref_%02d'%i).resize((cw,ch)); label(o,'ours t=%.2f'%to)
    g.paste(r,(c*(cw+4),0)); g.paste(o,(c*(cw+4),ch+4))
g.save(D+'skin_v7_motion_reference_vs_ours.jpg',quality=88); print('ref vs ours', g.size)
# (e) GIFs
frames=[ld('mo2_ref_%02d'%i).resize((640,360)) for i in range(48)]
frames[0].save(D+'skin_v7_motion_refview.gif',save_all=True,append_images=frames[1:],duration=83,loop=0,optimize=True)
frames=[ld('mo_pip_%02d'%i).resize((960,540)) for i in range(16)]
frames[0].save(D+'skin_v7_motion_pip.gif',save_all=True,append_images=frames[1:],duration=250,loop=0,optimize=True)
print('gifs', os.path.getsize(D+'skin_v7_motion_refview.gif')//1024, os.path.getsize(D+'skin_v7_motion_pip.gif')//1024, 'KB')
