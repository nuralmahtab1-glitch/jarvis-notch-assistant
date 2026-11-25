from PIL import Image, ImageDraw
import glob, os
fs=sorted(glob.glob('shots/[0-9]*.png'))
bg=(120,120,200)
tiles=[]
for f in fs:
    im=Image.open(f).convert('RGBA')
    base=Image.new('RGBA',im.size,bg+(255,))
    base.alpha_composite(im)
    base=base.crop((0,0,960,300)).resize((640,200))
    d=ImageDraw.Draw(base); d.text((6,186),os.path.basename(f),fill=(255,255,255))
    tiles.append(base)
w,h=tiles[0].size
for part in range(0,len(tiles),6):
    chunk=tiles[part:part+6]
    sheet=Image.new('RGB',(w*2,h*((len(chunk)+1)//2)),(40,40,60))
    for i,t in enumerate(chunk): sheet.paste(t.convert('RGB'),((i%2)*w,(i//2)*h))
    sheet.save(f'shots/sheet{part//6}.jpg',quality=90)
print(len(tiles))
