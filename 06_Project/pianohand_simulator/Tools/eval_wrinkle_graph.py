"""Evaluate the packed wrinkle-graph tables on a UV window exactly like PH_GraphCreases (rest state, all gates 1).

    venv/bin/python -I Tools/eval_wrinkle_graph.py <dir with T_PH_WrinkleGraph_*.png> <u> <v> <uv span> <out.png>

Grey = flat, dark = valley (0.08 cm full scale). 10-15: used to tell "the line is not in the table" from
"the GPU/gates/fade hide it" when the fine lattice would not show up.
"""
import sys, math, json
import numpy as np, cv2
D=sys.argv[1]; cu,cv=float(sys.argv[2]),float(sys.argv[3]); span=float(sys.argv[4]); out=sys.argv[5]
GRID=512; TW=4096; REL=6.0; WR=0.5; SCALE=25.272588
def ld(n):
    im=cv2.imread(D+'/'+n, cv2.IMREAD_UNCHANGED).astype(np.float64)/65535.0
    return im[..., [2,1,0,3]]  # BGRA -> RGBA
C=ld('T_PH_WrinkleGraph_Cells.png'); E0=ld('T_PH_WrinkleGraph_Edges0.png'); E1=ld('T_PH_WrinkleGraph_Edges1.png')
N=600
us=cu-span/2+np.arange(N)/N*span; vs=cv-span/2+np.arange(N)/N*span
H=np.zeros((N,N)); nfrag=np.zeros((N,N),int)
def prof(X):
    S=(X-1)*np.exp(-X); S=np.where(S>0,S*0.2,S)
    R=-1+0.45*X*X; T=np.clip(X/0.5,0,1); T=T*T*(3-2*T)
    return R*(1-T)+S*T
cells={}
for j,v in enumerate(vs):
    for i,u in enumerate(us):
        cx,cy=int(u*GRID),int(v*GRID)
        c=C[cy,cx]; start=int(round(c[0]*255))+(int(round(c[1]*255))<<8)+(int(round(c[3]*255))<<16); cnt=min(int(round(c[2]*255)),64)
        if cnt==0: continue
        centre=np.array([(cx+0.5)/GRID,(cy+0.5)/GRID]); cell=1.0/GRID
        sv=[]; sb=[]
        for k in range(cnt):
            idx=start+k; e0=E0[idx//TW, idx%TW]; e1=E1[idx//TW, idx%TW]
            P0=centre+(e0[:2]*2*REL-REL)*cell; P1=centre+(e0[2:]*2*REL-REL)*cell
            w=e1[0]; W=max(e1[1]*WR,1e-4); lvl=e1[3]*4
            seg=P1-P0; L2=max(seg@seg,1e-12); t=np.clip(((u-P0[0])*seg[0]+(v-P0[1])*seg[1])/L2,0,1)
            d=(np.array([u,v])-(P0+t*seg))*SCALE; L=math.hypot(*d); X=L/W
            if X>3.5: continue
            A=w*(0.6 if lvl<0.5 else 0.6*0.3*(10 if lvl>1.5 else 1))   # Depth 0.6, Sec 0.3, Fine 10, gates=1
            s=A*prof(X); (sv if s<0 else sb).append(abs(s))
        nfrag[j,i]=len(sv)+len(sb)
        V=(sum(x**8 for x in sv))**(1/8) if sv else 0; B=(sum(x**8 for x in sb))**(1/8) if sb else 0
        H[j,i]=B-V
print('H range %.4f %.4f, frag max %d, frac pixels with frag %.2f'%(H.min(),H.max(),nfrag.max(),(nfrag>0).mean()))
img=np.clip(128+H/0.08*127,0,255).astype(np.uint8)
cv2.imwrite(out, img)
