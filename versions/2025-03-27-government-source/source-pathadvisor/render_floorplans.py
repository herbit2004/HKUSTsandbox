"""Render the official vector plan geometry into north-up inspectable SVGs.
No geometry is inferred. SVG is a derived view; original GeoJSON remains canonical.
"""
from pathlib import Path
import json,math,html
ROOT=Path('/tmp/hkust-pathadvisor-complete')

def pts(a):
 if isinstance(a,list) and a:
  if isinstance(a[0],(int,float)):yield a
  else:
   for b in a:yield from pts(b)

def merc(p):return [6378137*math.radians(p[0]),6378137*math.log(math.tan(math.pi/4+math.radians(p[1])/2))]

def render(folder):
 m=json.load(open(folder/'manifest.json'));g=json.load(open(folder/'rooms.geojson'));cadfile=folder/'cad-lines.geojson';cad=json.load(open(cadfile)) if cadfile.exists() else {'features':[]}
 allpts=[merc(p) for f in g['features']+cad.get('features',[]) for p in pts(f.get('geometry',{}).get('coordinates',[]))]
 if not allpts:return None
 x0=min(p[0] for p in allpts);x1=max(p[0] for p in allpts);y0=min(p[1] for p in allpts);y1=max(p[1] for p in allpts)
 scale=min(1880/max(x1-x0,.1),1600/max(y1-y0,.1));w=round((x1-x0)*scale+80);h=round((y1-y0)*scale+150)
 def xy(p):
  x,y=merc(p);return f'{(x-x0)*scale+40:.3f},{(y1-y)*scale+100:.3f}'
 out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',f'<title>{html.escape(m["building_name"])} — {m["name"]}/F — HKUST Path Advisor official vector plan</title>','<rect width="100%" height="100%" fill="white"/>',f'<text x="40" y="32" font-size="18" font-family="sans-serif" font-weight="600">{html.escape(m["building_name"])} · {html.escape(m["name"])}/F</text>','<text x="40" y="56" font-size="12" font-family="sans-serif" fill="#555">HKUST Path Advisor · official room polygons and CAD lines · retrieved 2026-09-05 · north up</text>']
 for f in g['features']:
  geom=f.get('geometry',{});p=f.get('properties',{});t=geom.get('type');coord=geom.get('coordinates',[])
  polys=[coord] if t=='Polygon' else coord if t=='MultiPolygon' else []
  for poly in polys:
   d=' '.join('M'+' L'.join(xy(v) for v in ring)+' Z' for ring in poly if ring)
   color=p.get('type_color_hex') or 'eeeeee';color=''.join(c for c in color if c in '0123456789abcdefABCDEF')
   label='' if p.get('hidden_from_map') else (str(p.get('location_name') or '')+' '+str(p.get('type_name') or '')).strip()
   out.append(f'<path d="{d}" fill="#{color if len(color) in [3,6] else "eeeeee"}" fill-rule="evenodd" stroke="#999" stroke-width="0.35"><title>{html.escape(label)}</title></path>')
 # Keep CAD strokes; remove exact reversed duplicate two-point segments only.
 paths=[];seen=set()
 for f in cad.get('features',[]):
  ge=f.get('geometry',{});co=ge.get('coordinates',[]);lines=[co] if ge.get('type')=='LineString' else co if ge.get('type')=='MultiLineString' else []
  for line in lines:
   if len(line)<2:continue
   key=tuple(sorted((tuple(line[0]),tuple(line[1])))) if len(line)==2 else None
   if key is not None and key in seen:continue
   if key is not None:seen.add(key)
   paths.append('M'+' L'.join(xy(v) for v in line))
 out.append(f'<path d="{" ".join(paths)}" fill="none" stroke="#303944" stroke-width="0.42" stroke-linejoin="round"/>')
 out.append('</svg>');target=folder/'floor-plan.svg';target.write_text('\n'.join(out));return {'floor_id':m['_id'],'file':str(target.relative_to(ROOT)),'building':m['building_name'],'floor':m['name'],'svg_bytes':target.stat().st_size}
results=[]
for f in sorted((ROOT/'floors').glob('*/rooms.geojson')):
 r=render(f.parent)
 if r:results.append(r)
(ROOT/'svg-index.json').write_text(json.dumps(results,indent=2));print('SVG plans',len(results),'bytes',sum(x['svg_bytes'] for x in results))
