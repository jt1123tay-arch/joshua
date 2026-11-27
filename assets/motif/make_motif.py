"""Advantech square motif, rebuilt from the advantech.com parts:
   (1) a gradient-filled rounded tile, (2) a chain of three gradient-stroked frames.
   The site composite = tile at ~20% opacity + the top two frames at ~64% opacity."""
import math, sys
OUT = sys.argv[1]
ROT = 23; r = math.radians(ROT); u = (math.cos(r), math.sin(r)); v = (-math.sin(r), math.cos(r))
S = 70.5; SW = 4.5; RF = 10.0                       # frame side (centre-line), stroke, corner radius (px)
F0 = (182.5, 93.1); F1 = (240.2, 61.5)               # lower-left and upper-right frames (measured)
F2 = (F0[0] + S * (0.37 * u[0] + 0.89 * v[0]), F0[1] + S * (0.37 * u[1] + 0.89 * v[1]))   # third frame below
ST = 270.0; RT = 0.16 * ST                           # tile side and corner radius (source tile proportion)
TC = (60 + ST / 2 * (u[0] + v[0]), 48.5 + ST / 2 * (u[1] + v[1]))   # tile's top-left corner sits at (60, 48.5)
EXT = lambda side: side * (math.cos(r) + math.sin(r)) / 2
C = dict(t0='#02427A', t1='#278EE1', f0='#044A89', f1='#288DDE')

def rect(c, side, rad, attrs):
    return (f'<rect x="{c[0]-side/2:.2f}" y="{c[1]-side/2:.2f}" width="{side:.2f}" height="{side:.2f}" rx="{rad:.2f}" '
            f'transform="rotate({ROT} {c[0]:.2f} {c[1]:.2f})" {attrs}/>')

def svg(parts, name, pal=C, ta=1.0, fa=1.0, scale=4):
    els = []
    for kind, c in parts:
        if kind == 'tile': els.append((c, ST))
        else: els.append((c, S + SW))
    xs = [c[0] - EXT(sd) for c, sd in els] + [c[0] + EXT(sd) for c, sd in els]
    ys = [c[1] - EXT(sd) for c, sd in els] + [c[1] + EXT(sd) for c, sd in els]
    M = 6; x0, y0 = min(xs) - M, min(ys) - M; W, H = max(xs) - min(xs) + 2 * M, max(ys) - min(ys) + 2 * M
    fx0 = min(c[0] - EXT(S + SW) for k, c in parts if k == 'frame') if any(k == 'frame' for k, _ in parts) else 0
    fx1 = max(c[0] + EXT(S + SW) for k, c in parts if k == 'frame') if any(k == 'frame' for k, _ in parts) else 1
    body = []
    for kind, c in parts:
        if kind == 'tile':
            body.append(rect(c, ST, RT, f'fill="url(#tile)" fill-opacity="{ta}"'))
        else:
            body.append(rect(c, S, RF, f'fill="none" stroke="url(#frame)" stroke-opacity="{fa}" stroke-width="{SW}"'))
    out = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W*scale:.0f}" height="{H*scale:.0f}" viewBox="{x0:.2f} {y0:.2f} {W:.2f} {H:.2f}">\n'
           f'  <defs>\n'
           f'    <linearGradient id="tile" gradientUnits="userSpaceOnUse" x1="{TC[0]-EXT(ST):.1f}" y1="0" x2="{TC[0]+EXT(ST):.1f}" y2="0">'
           f'<stop offset="0" stop-color="{pal["t0"]}"/><stop offset="1" stop-color="{pal["t1"]}"/></linearGradient>\n'
           f'    <linearGradient id="frame" gradientUnits="userSpaceOnUse" x1="{fx0:.1f}" y1="0" x2="{fx1:.1f}" y2="0">'
           f'<stop offset="0" stop-color="{pal["f0"]}"/><stop offset="1" stop-color="{pal["f1"]}"/></linearGradient>\n'
           f'  </defs>\n  ' + '\n  '.join(body) + '\n</svg>\n')
    open(OUT + name + '.svg', 'w').write(out)

DARK = dict(t0='#2D6BB0', t1='#4A9BEA', f0='#4A8FD6', f1='#9CCBF6')
svg([('tile', TC)], 'advantech_motif_part_tile')                                      # source part 1, opaque
svg([('frame', F1), ('frame', F0), ('frame', F2)], 'advantech_motif_part_frames')      # source part 2, opaque
svg([('tile', TC), ('frame', F0), ('frame', F1)], 'advantech_square_motif_light', ta=0.20, fa=0.64)
svg([('tile', TC), ('frame', F0), ('frame', F1)], 'advantech_square_motif_dark', pal=DARK, ta=0.22, fa=0.80)
print('F2', F2, 'TC', TC)
