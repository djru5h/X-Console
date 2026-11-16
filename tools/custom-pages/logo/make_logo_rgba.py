import numpy as np
from PIL import Image, ImageFilter, ImageDraw
src=Image.open('/mnt/g/claude/mpc/plugins/Gen 2/X-Console/pictures/Metallic X-Console Hearts Banner.png').convert('RGB')
a=np.asarray(src).astype(np.float32)
mn=a.min(2)
cand=Image.fromarray(((mn>228)*255).astype(np.uint8)).copy()
Wd,Hd=cand.size
px=cand.load()
pts=[(x,0) for x in range(Wd)]+[(x,Hd-1) for x in range(Wd)]+[(0,y) for y in range(Hd)]+[(Wd-1,y) for y in range(Hd)]
for p in pts:
    if px[p]==255: ImageDraw.floodfill(cand,p,128)
bg=np.asarray(cand)==128
fgimg=Image.fromarray(((~bg)*255).astype(np.uint8))
core=np.asarray(fgimg.filter(ImageFilter.MinFilter(5)))>0   # fg eroded 2px
alpha=np.where(core,1.0,np.clip((255-mn)/105.0,0,1))
alpha[bg]=np.clip((255-mn[bg])/105.0,0,1)*0.0
alpha=np.asarray(Image.fromarray((alpha*255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6)),np.float32)/255
al=alpha[...,None]
rgb=np.clip((a-255*(1-al))/np.maximum(al,0.05),0,255)
out=np.dstack([rgb,alpha*255]).astype(np.uint8)
Image.fromarray(out,'RGBA').save('logo_rgba.png')
ys=np.where(alpha.max(1)>0.05)[0]; xs=np.where(alpha.max(0)>0.05)[0]; print(xs[0],xs[-1],ys[0],ys[-1])
for c,nm in [((30,32,36),'dark'),((40,120,200),'blue')]:
    b=Image.new('RGBA',src.size,c+(255,)); b.alpha_composite(Image.fromarray(out,'RGBA'))
    b.crop((0,250,1100,520)).convert('RGB').save('test_%s.png'%nm)
