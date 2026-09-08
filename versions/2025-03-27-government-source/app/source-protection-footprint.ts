import type { PolygonPart, PointXZ } from './source-types';

// Float32 world-space boundary tolerance (0.1 mm), not a geographic expansion.
const epsilon = 0.0001;
function ringStatus(x: number, z: number, ring: PointXZ[]): 0 | 1 | 2 {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[j], b = ring[i], dx = b[0] - a[0], dz = b[1] - a[1];
    const lengthSquared = dx * dx + dz * dz;
    const t = lengthSquared ? Math.min(1, Math.max(0, ((x - a[0]) * dx + (z - a[1]) * dz) / lengthSquared)) : 0;
    if (Math.hypot(x - a[0] - t * dx, z - a[1] - t * dz) <= epsilon) return 2;
    if ((a[1] > z) !== (b[1] > z) && x < a[0] + (z - a[1]) * dx / dz) inside = !inside;
  }
  return inside ? 1 : 0;
}

/** Source multipolygon union with holes; polygon and hole boundaries belong. */
export function insideSourceProtection(x: number, z: number, parts: PolygonPart[]) {
  return parts.some(part => {
    const outer = ringStatus(x, z, part.rings[0]);
    if (!outer) return false;
    const holes = part.rings.slice(1).map(ring => ringStatus(x, z, ring));
    return outer === 2 || holes.includes(2) || !holes.includes(1);
  });
}

/** Constants consume no additional texture or uniform slots. CPU and shader
 * use the same finite segment-distance boundary and even-odd ring predicates. */
export function sourceProtectionFootprintGLSL(parts: PolygonPart[]) {
  const number = (v: number) => {
    if (!Number.isFinite(v)) throw new Error('Non-finite source protection vertex');
    const s = v.toFixed(9); return s;
  };
  let source = `
int campusSourceEdge(vec2 q,vec2 a,vec2 b,inout bool inside) {
  vec2 d=b-a; float l=dot(d,d);
  float t=l>0.0?clamp(dot(q-a,d)/l,0.0,1.0):0.0;
  if(length(q-a-t*d)<=0.0001) return 2;
  if((a.y>q.y)!=(b.y>q.y) && q.x<a.x+(q.y-a.y)*d.x/d.y) inside=!inside;
  return 0;
}
`;
  let index = 0;
  const expressions = parts.map(part => {
    const names = part.rings.map(ring => {
      if (ring.length < 3) throw new Error('Invalid source protection ring');
      const name = `campusSourceRing${index++}`;
      source += `int ${name}(vec2 q){bool inside=false;\n`;
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const a = ring[j], b = ring[i];
        source += `if(campusSourceEdge(q,vec2(${number(a[0])},${number(a[1])}),vec2(${number(b[0])},${number(b[1])}),inside)==2)return 2;\n`;
      }
      source += 'return inside?1:0;}\n';
      return name;
    });
    const holes = names.slice(1);
    return `(${names[0]}(q)>0 && (${names[0]}(q)==2${holes.map(n => `||${n}(q)==2`).join('')} || (${holes.map(n => `${n}(q)!=1`).join('&&') || 'true'})))`;
  });
  return source + `bool campusInsideSourceProtection(vec2 q){return ${expressions.join('||') || 'false'};}\n`;
}
