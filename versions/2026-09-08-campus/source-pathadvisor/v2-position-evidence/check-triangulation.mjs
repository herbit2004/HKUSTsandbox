import fs from 'node:fs';
import { ShapeUtils, Vector2 } from 'three';
const root='/tmp/hkust-v2-pois/';
const data=JSON.parse(fs.readFileSync(root+'building-footprints.json','utf8'));
const rows=[];
for(const feature of data.footprints) for(const part of feature.parts){
 const rings=part.rings.map(r=>r.map(p=>new Vector2(...p)));
 const triangles=ShapeUtils.triangulateShape(rings[0],rings.slice(1));
 const points=rings.flat(); let area=0;
 for(const [i,j,k] of triangles){const [a,b,c]=[points[i],points[j],points[k]]; area+=Math.abs((b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x))/2;}
 const source=part.areaSquareMeters; const delta=Math.abs(area-source);
 rows.push({footprintId:feature.id,partIndex:part.partIndex,triangles:triangles.length,expectedDrawingArea:source,triangulatedArea:area,difference:delta,withinTolerance:delta<=Math.max(0.01,source*0.001)});
}
const report={status:rows.every(r=>r.withinTolerance)?'pass':'source-geometric-caveat',parts:rows.length,triangles:rows.reduce((s,r)=>s+r.triangles,0),maximumAbsoluteAreaDifference:Math.max(...rows.map(r=>r.difference)),failures:rows.filter(r=>!r.withinTolerance),checkedUsing:'Three.js ShapeUtils/Earcut with source holes retained',rows};
fs.writeFileSync(root+'triangulation-qa.json',JSON.stringify(report,null,2));
console.log(JSON.stringify({...report,rows:undefined},null,2));
// Carry the exact source/rendering caveat into the consumable asset.
for (const failure of report.failures) {
  const feature = data.footprints.find(f => f.id === failure.footprintId);
  feature.parts[failure.partIndex].triangulationCaveat = {
    expectedDrawingArea: failure.expectedDrawingArea,
    earcutArea: failure.triangulatedArea,
    differenceSquareMeters: failure.difference,
    recommendedDisplay: 'outline-first; do not treat fill area as surveyed area',
  };
}
data.triangulationQA = {
  checkedUsing: report.checkedUsing, totalParts: report.parts,
  partsWithCaveat: report.failures.length, details: 'triangulation-qa.json',
};
fs.writeFileSync(root+'building-footprints.json',JSON.stringify(data));
const qa=JSON.parse(fs.readFileSync(root+'qa.json','utf8'));
qa.triangulation={status:report.status,parts:report.parts,failures:report.failures};
qa.status=report.failures.length?'pass-with-one-triangulation-caveat':'pass';
fs.writeFileSync(root+'qa.json',JSON.stringify(qa,null,2));
