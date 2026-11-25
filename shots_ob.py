from PIL import Image, ImageDraw
import glob, os, sys
fs = sorted(glob.glob('shots/ob/onboarding_*.png'))
tiles = []
for f in fs:
    im = Image.open(f).convert('RGBA'); bg = Image.new('RGBA', im.size, (90, 90, 140, 255)); bg.alpha_composite(im)
    w, h = bg.size; bg = bg.resize((w // 2, h // 2)).convert('RGB')
    ImageDraw.Draw(bg).text((8, 4), os.path.basename(f), fill=(255, 255, 255)); tiles.append(bg)
w, h = tiles[0].size
for part in range(0, len(tiles), 6):
    ch = tiles[part:part + 6]; sh = Image.new('RGB', (w * 3, h * ((len(ch) + 2) // 3)))
    for i, t in enumerate(ch): sh.paste(t, ((i % 3) * w, (i // 3) * h))
    sh.save(f'shots/ob/sheet{part // 6}.jpg', quality=88)
print(len(tiles), tiles[0].size)
