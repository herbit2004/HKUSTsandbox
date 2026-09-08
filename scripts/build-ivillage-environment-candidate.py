#!/usr/bin/env python3
"""Build a deliberately small, independently loadable i-Village ground candidate.

Only the two official exterior witnesses justify the features here. Coordinates
are source-local and dimensions are approximate; existing terrain, roads,
trees, masks and Hall X-XIII geometry are untouched.
"""
import argparse, hashlib, json
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon, LineString, shape
from shapely.ops import unary_union
from ivillage_geometry import BuildingMesh, write_glb

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--stage',type=Path,default=Path('/tmp/hkust-ivillage-rebuild-source'))
    ap.add_argument('--output',type=Path,default=Path('public/models/current-forms/ivillage-rebuild/environment-candidate'))
    a=ap.parse_args(); root=Path(__file__).resolve().parents[1]; out=(root/a.output).resolve(); out.mkdir(parents=True,exist_ok=True)
    grid=np.load(a.stage/'roof-grid.npz'); ground=grid['ground']; x0,z0,step=map(float,[grid['x0'],grid['z0'],grid['step']])
    def gy(x,z):
        c=int(np.clip(np.floor((x-x0)/step),0,ground.shape[1]-1)); r=int(np.clip(np.floor((z-z0)/step),0,ground.shape[0]-1)); return float(ground[r,c])
    # Existing normalized Hall envelopes are hard exclusion domains.  The
    # candidate must never become a floor/road/vegetation cover over them.
    features=json.loads((a.stage/'normalized-envelopes.geojson').read_text())['features']
    halls=unary_union([shape(f['geometry']) for f in features])
    exclusion=halls.buffer(1.0)
    mesh=BuildingMesh('environment:ivillage-ground-candidate','ivillage-ground-candidate','ivillage-ground-environment')
    # Broad paved courtyard/platform visible in 098; extent and grade are approximate.
    platform=Polygon([(650,-1090),(756,-1090),(778,-1050),(665,-1042)]).difference(exclusion)
    mesh.surface(platform,lambda x,z:gy(x,z)+.06,2,'official-098-paved-platform')
    # Planted strip retained as a low surface inside the platform; no foliage volumes.
    planted=Polygon([(670,-1076),(744,-1077),(752,-1060),(680,-1055)]).difference(exclusion)
    mesh.surface(planted,lambda x,z:gy(x,z)+.10,1,'official-027-planted-bed-approx')
    # Low perimeter/terrace edges visible in 027. No claim that these are cadastral walls.
    outer=LineString([(650,-1090),(756,-1090),(778,-1050),(665,-1042),(650,-1090)]).difference(exclusion)
    for edge in getattr(outer,'geoms',[outer]):
        if edge.geom_type!='LineString': continue
        pts=list(edge.coords)
        for s,e in zip(pts,pts[1:]): mesh.wall(s,e,lambda x,z:gy(x,z)+.06,lambda x,z:gy(x,z)+.76,1,'official-027-low-white-edge-wall-approx')
    tex=out/'official-roof-paving.png'; import shutil; shutil.copy2(root/'public/models/current-forms/ivillage-rebuild/textures/official-roof-paving.png',tex)
    prov={'representationSet':'hkust-ivillage-ground-environment-candidate-v2','method':'two official 2026 exterior witnesses + source DTM height samples + hard subtraction of all four existing Hall footprints','approximateFeatures':['platform extent and grade','planted bed extent','low edge-wall height'],'excluded':['roads','trees/canopy','Hall X-XIII masks','door/opening geometry','hidden retaining walls','sports-court boundary'],'sourceURLs':['https://cdo.hkust.edu.hk/projects/jockey-club-i-village','https://cdo.hkust.edu.hk/sites/default/files/2026-07/098.HKUST-iVillage_Photos-DJI_0001-Pano_LR.jpg','https://cdo.hkust.edu.hk/sites/default/files/2026-07/027.HKUST-iVillage_Photos-T7405869_LR.jpg'],'footprintExclusionBufferM':1.0}
    info=write_glb(out/'ivillage-ground-environment-candidate.glb',[mesh],tex,prov,photographic=False,paving_path=tex)
    manifest={'version':1,'id':prov['representationSet'],'asset':info,'coordinateSystem':'x=E-844800,y=source-local vertical,z=820500-N','features':[{'name':'official-098-paved-platform','material':'roof-paving','confidence':'direct visual witness; extent approximate'},{'name':'official-027-planted-bed-approx','material':'neutral edge proxy','confidence':'direct visual witness; footprint approximate'},{'name':'official-027-low-white-edge-wall-approx','material':'neutral low wall','confidence':'direct visual witness; height approximate'}],'limitations':prov['excluded']+prov['approximateFeatures'],'source':prov['sourceURLs'],'offlinePreviews':'../../previews/*.png','noPreviewPublication':True}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n'); print(json.dumps(manifest,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
